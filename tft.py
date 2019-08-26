import json
import glob
import mmap
import copy
import re
import os
from json import JSONEncoder
from cdragontoolbox.binfile import BinFile, BinHashBase, BinHashValue


class NaiveJsonEncoder(JSONEncoder):
    def default(self, other):  # pylint: disable=method-hidden
        if isinstance(other, BinHashBase):
            if other.s is None:
                return other.hex()
            return other.s
        return other.__dict__


class TFTTransformer:
    def parse(self, input):
        map22_file = os.path.join(input, "data", "maps", "shipping", "map22", "map22.bin")
        character_folder = os.path.join(input, "data", "characters")

        map22 = BinFile(map22_file)
        items = self.parse_items(map22)
        traits = self.parse_traits(map22)
        champs = self.parse_champs(map22, traits, character_folder)

        # clean up data for JSON export
        [x.pop("internal") for x in traits]
        [x.pop("internal") for x in items]

        self.data = {"items": items, "traits": traits, "champs": champs}

    def export(self, output, font_files=[], output_template=False):
        os.makedirs(output, exist_ok=True)
        template = json.dumps(self.data, cls=NaiveJsonEncoder, indent=4, sort_keys=True)

        if output_template:
            with open(os.path.join(output, "template.json"), "w", encoding="utf-8") as f:
                f.write(template)

        for language in font_files:
            use = template
            code = os.path.basename(language)[11:-4]

            with open(language, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("tr"):
                        key, val = line.split("=", 1)
                        key = key[4:-2]
                        val = val[2:-2]
                        use = use.replace(key, val)

            with open(os.path.join(output, code + ".json"), "w", encoding="utf-8") as f:
                f.write(use)

    def parse_items(self, map22):
        item_collection = [x for x in map22.entries if x.type == "TftItemData"]
        items = []

        for item in item_collection:
            name = item.getv("mName")
            if "Template" in name or name == "TFT_Item_Null":
                continue

            effects = []
            for effect in item.getv("effectAmounts") if item.get("effectAmounts") else []:
                effects.append({"name": effect.getv("name"), "value": effect.getv("value")})

            items.append(
                {
                    "internal": {"hex": item.path.hex(), "name": item.getv("mName")},
                    "id": item.getv("mId"),
                    "name": item.getrv("c3143d66"),
                    "desc": item.getrv("765f18da"),
                    "icon": item.getv("mIconPath"),
                    "from": [x.hex() for x in item.getrv("8b83ba8a")] if item.getr("8b83ba8a") else [],
                    "effects": effects,
                }
            )

        # replace the hex key gotten earlier with the id
        for item in items:
            # there must be some list comprehension way of doing this...
            for old in item["from"]:
                key = [x for x in items if x["internal"]["hex"] == old][0]["id"]
                item["from"].insert(0, key)
                item["from"].remove(old)

        return items

    def parse_champs(self, map22, traits, character_folder):
        champ_collection = [x for x in map22.entries if x.type == "TftShopData"]
        champs = []

        for champ in champ_collection:
            name = champ.getv("mName")

            if not name.startswith("TFT_") or name == "TFT_Template":
                continue

            char_bin = BinFile(os.path.join(character_folder, name[4:], name[4:] + ".bin"))
            champ_id = [x.getv("characterToolData").getv("championId") for x in char_bin.entries if x.type == "CharacterRecord"][0]

            champ_traits = []
            tft_bin = BinFile(os.path.join(character_folder, name, name + ".bin"))
            record = [x for x in tft_bin.entries if x.type == "TFTCharacterRecord"][0]
            for trait in record.getv("mLinkedTraits"):
                champ_traits.append([x["internal"]["name"] for x in traits if x["internal"]["hash"] == trait.hex()][0])

            stats_obj = {
                "hp": record.getv("baseHP"),
                "mana": record.getv("primaryAbilityResource").getv("arBase"),
                "initialMana": record.getv("mInitialMana") or 0,
                "damage": record.getv("BaseDamage"),
                "armor": record.getv("baseArmor"),
                "magicResist": record.getv("baseSpellBlock"),
                "critMultiplier": record.getv("critDamageMultiplier"),
                "critChance": record.getv("baseCritChance"),
                "attackSpeed": record.getv("attackSpeed"),
                "range": record.getv("attackRange") // 180,
            }

            spell_name = record.getv("spellNames")[0]
            if "/" in spell_name:
                spell_name = os.path.basename(spell_name)
            ability = [x.getv("mSpell") for x in tft_bin.entries if x.type == "SpellObject" and x.getv("mScriptName") == spell_name][0]

            variables = []
            for value in ability.getv("mDataValues"):
                variables.append({"name": value.getv("mName"), "value": value.getv("mValues")})

            ability_obj = {"name": champ.getrv("87a69a5e"), "desc": champ.getrv("bc4f18b3"), "icon": champ.getv("mPortraitIconPath"), "variables": variables}

            champs.append(
                {
                    "id": champ_id,
                    "name": champ.getrv("c3143d66"),
                    "cost": champ.getv("mRarity") or 1,
                    "icon": champ.getv("mIconPath"),
                    "traits": champ_traits,
                    "stats": stats_obj,
                    "ability": ability_obj,
                }
            )

        return champs

    def parse_traits(self, map22):
        trait_collection = [x for x in map22.entries if x.type == "TftTraitData"]
        traits = []

        for trait in trait_collection:
            if "Template" in trait.getv("mName"):
                continue

            effects = []
            for trait_set in trait.getv("mTraitSets"):
                variables = []
                for effect in trait_set.getv("effectAmounts") if trait_set.get("effectAmounts") else []:
                    variables.append({"name": effect.getv("name"), "value": effect.getv("value")})

                effects.append({"minUnits": trait_set.getv("mMinUnits"), "maxUnits": trait_set.getv("mMaxUnits"), "variables": variables})

            traits.append(
                {
                    "internal": {"hash": trait.path.hex(), "name": trait.getv("mName")},
                    "name": trait.getrv("c3143d66"),
                    "desc": trait.getrv("765f18da"),
                    "icon": trait.getv("mIconPath"),
                    "effects": effects,
                }
            )

        return traits


if __name__ == "__main__":
    input_folder = os.path.join("D:", "pbe")
    output_folder = os.path.join("D:", "pbe", "tft_temp")

    font_folder = os.path.join(input_folder, "data", "menu")
    lang_files = glob.glob(f"{font_folder}/fontconfig_*_*.txt")

    tft_transformer = TFTTransformer()
    tft_transformer.parse(input_folder)
    tft_transformer.export(output_folder, lang_files, True)
