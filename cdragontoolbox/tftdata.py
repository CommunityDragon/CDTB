import json
import glob
import os
from .binfile import BinFile, BinHashBase, BinHashValue, BinEmbedded


class NaiveJsonEncoder(json.JSONEncoder):
    def default(self, other):
        if isinstance(other, BinHashBase):
            if other.s is None:
                return other.hex()
            return other.s
        return other.__dict__


class TftTransformer:
    def __init__(self, input_dir):
        self.input_dir = input_dir

    def build_template(self):
        """Parse bin data into template data"""
        map22_file = os.path.join(self.input_dir, "data", "maps", "shipping", "map22", "map22.bin")
        character_folder = os.path.join(self.input_dir, "data", "characters")

        map22 = BinFile(map22_file)
        items = self.parse_items(map22)
        traits = self.parse_traits(map22)
        champs = self.parse_champs(map22, traits, character_folder)

        # clean up data for JSON export
        [x.pop("internal") for x in traits]
        [x.pop("internal") for x in items]

        return {"items": items, "traits": traits, "champs": champs}

    def export(self, output, langs=None):
        """Export TFT data for given languages

        By default (`langs` is `None`), export all available languages.
        Otherwise, export for given `xx_yy` language codes.
        """

        fontconfig_dir = os.path.join(self.input_dir, "data/menu")

        if langs is None:
            langs = []
            for path in glob.glob(os.path.join(fontconfig_dir, "fontconfig_??_??.txt")):
                langs.append(path[-9:-4])

        os.makedirs(output, exist_ok=True)

        template = self.build_template()
        for lang in langs:
            replacements = {}
            with open(os.path.join(fontconfig_dir, f"fontconfig_{lang}.txt"), encoding="utf-8") as f:
                for line in f:
                    if line.startswith("tr"):
                        key, val = line.split("=", 1)
                        key = key[4:-2]
                        val = val[2:-2]
                        replacements[key] = val

            def replace_in_data(data):
                for key in ("name", "desc"):
                    if key in data and data[key] in replacements:
                        data[key] = replacements[data[key]]

            for data in template["champs"]:
                replace_in_data(data)
                if "ability" in data:
                    replace_in_data(data["ability"])
            for data in template["items"]:
                replace_in_data(data)
            for data in template["traits"]:
                replace_in_data(data)

            with open(os.path.join(output, f"{lang}.json"), "w", encoding="utf-8") as f:
                json.dump(template, f, cls=NaiveJsonEncoder, indent=4, sort_keys=True)

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
            champ_traits = []
            for trait in record.getv("mLinkedTraits", []):
                if isinstance(trait, BinEmbedded):
                    champ_traits.extend(trait_names[field.value.h] for field in trait.fields)
                else:
                    champ_traits.append(trait_names[trait.h])

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
                    "cost": champ.getv("mRarity", 0) + 1,
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
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="directory with extracted bin files")
    parser.add_argument("-o", "--output", default="tft", help="output directory")
    args = parser.parse_args()

    tft_transformer = TftTransformer(args.input)
    tft_transformer.export(args.output, langs=None)
