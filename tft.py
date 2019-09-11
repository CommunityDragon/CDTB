import argparse
import json
import glob
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


class TftTransformer:
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

    def export(self, output, font_files=None, output_template=False):
        os.makedirs(output, exist_ok=True)
        template = json.dumps(self.data, cls=NaiveJsonEncoder, indent=4, sort_keys=True)

        if output_template:
            with open(os.path.join(output, "template.json"), "w", encoding="utf-8") as f:
                f.write(template)

        if not font_files:
            return

        for language in font_files:
            use = template
            code = os.path.basename(language)[11:-4]

            with open(language, encoding="utf-8") as f:
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
            for effect in item.getv("effectAmounts", []):
                effects.append({"name": effect.getv("name"), "value": effect.getv("value")})

            items.append(
                {
                    "internal": {"hex": item.path.h, "name": item.getv("mName")},
                    "id": item.getv("mId"),
                    "name": item.getv(0xC3143D66),
                    "desc": item.getv(0x765F18DA),
                    "icon": item.getv("mIconPath"),
                    "from": [x.h for x in item.getv(0x8B83BA8A, [])],
                    "effects": effects,
                }
            )

        item_ids = {x["internal"]["hex"]: x["id"] for x in items}
        for item in items:
            item["from"] = [item_ids[x] for x in item["from"]]

        return items

    def parse_champs(self, map22, traits, character_folder):
        champ_collection = [x for x in map22.entries if x.type == "TftShopData"]
        champs = []

        trait_names = {x["internal"]["hash"]: x["internal"]["name"] for x in traits}

        for champ in champ_collection:
            name = champ.getv("mName")

            if not name.startswith("TFT_") or name == "TFT_Template":
                continue

            char_bin = BinFile(os.path.join(character_folder, name[4:], name[4:] + ".bin").lower())
            champ_id = [x.getv("characterToolData").getv("championId") for x in char_bin.entries if x.type == "CharacterRecord"][0]

            tft_bin = BinFile(os.path.join(character_folder, name, name + ".bin").lower())
            record = [x for x in tft_bin.entries if x.type == "TFTCharacterRecord"][0]
            champ_traits = [trait_names[trait.h] for trait in record.getv("mLinkedTraits", [])]

            stats_obj = {
                "hp": record.getv("baseHP"),
                "mana": record.getv("primaryAbilityResource").getv("arBase", 100),
                "initialMana": record.getv("mInitialMana", 0),
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

            ability_obj = {"name": champ.getv(0x87A69A5E), "desc": champ.getv(0xBC4F18B3), "icon": champ.getv("mPortraitIconPath"), "variables": variables}

            champs.append(
                {
                    "id": champ_id,
                    "name": champ.getv(0xC3143D66),
                    "cost": champ.getv("mRarity", 1),
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
                for effect in trait_set.getv("effectAmounts", []):
                    variables.append({"name": effect.getv("name"), "value": effect.getv("value")})

                effects.append({"minUnits": trait_set.getv("mMinUnits"), "maxUnits": trait_set.getv("mMaxUnits"), "variables": variables})

            traits.append(
                {
                    "internal": {"hash": trait.path.h, "name": trait.getv("mName")},
                    "name": trait.getv(0xC3143D66),
                    "desc": trait.getv(0x765F18DA),
                    "icon": trait.getv("mIconPath"),
                    "effects": effects,
                }
            )

        return traits


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="directory with extracted bin files")
    parser.add_argument("-o", "--output", default="tft", help="output directory")
    args = parser.parse_args()

    font_folder = os.path.join(args.input, "data", "menu")
    lang_files = glob.glob(f"{font_folder}/fontconfig_*_*.txt")

    tft_transformer = TftTransformer()
    tft_transformer.parse(args.input)
    tft_transformer.export(args.output, lang_files, True)
