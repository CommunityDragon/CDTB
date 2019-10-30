import math
import json
import glob
import os
import copy
from .binfile import BinFile, BinHashBase, BinEmbedded


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
        character_lookup = self.parse_lookup_table(map22)
        sets = self.parse_sets(map22, character_lookup)
        traits = self.parse_traits(map22)
        champs = self.parse_champs(map22, traits, character_folder)
        output_sets = self.generate_correct_set_info(sets, traits, champs)

        items = self.parse_items(map22)
        [x.pop("internal") for x in items]

        return {"sets": output_sets, "items": items}

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
            instance = copy.deepcopy(template)
            replacements = {}
            with open(os.path.join(fontconfig_dir, f"fontconfig_{lang}.txt"), encoding="utf-8") as f:
                for line in f:
                    if line.startswith("tr"):
                        key, val = line.split("=", 1)
                        key = key[4:-2]
                        val = val[2:-2]
                        replacements[key] = val

            def replace_in_data(entry):
                for key in ("name", "desc"):
                    if key in entry and entry[key] in replacements:
                        entry[key] = replacements[entry[key]]

            for data in (y for x in instance["sets"].values() for y in x["traits"]):
                replace_in_data(data)
            for data in (y for x in instance["sets"].values() for y in x["champions"]):
                replace_in_data(data)
                if "ability" in data:
                    replace_in_data(data["ability"])
            for data in instance["items"]:
                replace_in_data(data)

            with open(os.path.join(output, f"{lang}.json"), "w", encoding="utf-8") as f:
                json.dump(instance, f, cls=NaiveJsonEncoder, indent=4)

    def generate_correct_set_info(self, sets, traits, champs):

        set_map = {}
        for key, value in sets.items():
            current_set = {"name": value["name"]}

            set_champs = []
            for char_name in value["internal"]["characters"]:
                for real_char in champs:
                    if char_name == real_char["internal"]["name"]:
                        set_champs.append(real_char)

            set_traits = {y for x in set_champs for y in x["traits"]}

            if len(sets) > 1:
                set_traits = [x for x in traits for y in set_traits if y == x["internal"]["hash"]]
            else:
                set_traits = [x for x in traits]

            for champ in set_champs:
                champ["traits"] = [x["name"] for x in traits if x["internal"]["hash"] in champ["traits"]]

            current_set["traits"] = set_traits
            current_set["champions"] = set_champs
            set_map[key] = current_set

        [x.pop("internal") for y in set_map for x in set_map[y]["champions"]]
        [x.pop("internal") for y in set_map for x in set_map[y]["traits"]]

        return set_map

    def parse_lookup_table(self, map22):
        return {x.path: x.getv("name") for x in map22.entries if x.type == "Character"}

    def parse_sets(self, map22, character_lookup):
        character_lists = {x.path: x for x in map22.entries if x.type == "MapCharacterList"}
        set_collection = [x for x in map22.entries if x.type == 0x438850FF]
        sets = {}

        if not set_collection:
            champion_list = max(character_lists.values(), key=lambda coll: len(coll.fields[0].value)).fields[0].value
            set_characters = []

            for char in champion_list:
                set_characters.append(character_lookup[char] if char in character_lookup else None)

            sets[1] = {
                "name": "Base",
                "internal": {"characters": set_characters}
            }

        for item in set_collection:
            char_list = item.getv("characterLists")[0]
            set_info = item[0xD2538E5A].value
            set_no = set_info["SetNumber"]["mValue"].value
            set_name = set_info["SetName"]["mValue"].value
            set_characters = []

            if char_list not in character_lists:
                continue

            chars = character_lists[char_list].getv("Characters")
            for char in chars:
                set_characters.append(character_lookup[char])

            sets[set_no] = {"name": set_name, "internal": {"characters": set_characters}}
        return sets

    def parse_items(self, map22):
        item_collection = [x for x in map22.entries if x.type == "TftItemData"]
        items = []

        for item in item_collection:
            name = item.getv("mName")
            if "Template" in name or name == "TFT_Item_Null":
                continue

            effects = {}
            for effect in item.getv("effectAmounts", []):
                name = effect.getv("name").s if "name" in effect else effect.path.hex()
                effects[name] = effect.getv("value", "null")

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

    def find_closest_path(self, parent, name):
        test = name
        while test:
            path = os.path.join(parent, test, test + ".bin")
            if os.path.exists(path):
                return path

            test = test[:-1]

        return None

    def parse_champs(self, map22, traits, character_folder):
        champ_collection = [x for x in map22.entries if x.type == "TftShopData"]
        champs = []

        for champ in champ_collection:
            name = champ.getv("mName")

            if name in ["TFT_Template", "Sold", "SellAction", "GetXPAction", "RerollAction", "LockAction"]:
                continue

            real_name = name.rsplit("_", 1)[-1]
            closest_path = self.find_closest_path(character_folder, real_name)
            char_bin = BinFile(closest_path)
            champ_id = [x.getv("characterToolData").getv("championId") for x in char_bin.entries if x.type == "CharacterRecord"][0]

            self_path = os.path.join(character_folder, name, name + ".bin")
            if not os.path.exists(self_path):
                continue

            tft_bin = BinFile(self_path)
            record = [x for x in tft_bin.entries if x.type == "TFTCharacterRecord"][0]
            champ_traits = []
            for trait in record.getv("mLinkedTraits", []):
                if isinstance(trait, BinEmbedded):
                    champ_traits.extend(field.value for field in trait.fields if field.name.h == 0x053A1F33)
                else:
                    champ_traits.append(trait.h)

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

            rarity = champ.getv("mRarity", 0) + 1
            increment = math.floor(rarity / 6)
            champs.append(
                {
                    "id": champ_id,
                    "name": champ.getv(0xC3143D66),
                    "cost": rarity + increment,
                    "icon": champ.getv("mIconPath"),
                    "traits": champ_traits,
                    "stats": stats_obj,
                    "ability": ability_obj,
                    "internal": {"name": name},
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
                variables = {}
                for effect in trait_set.getv("effectAmounts", []):
                    name = str(effect.getv("name")) if "name" in effect else "null"
                    variables[name] = effect.getv("value", "null")

                effects.append({"minUnits": trait_set.getv("mMinUnits"), "maxUnits": trait_set.getv("mMaxUnits") or 25000, "variables": variables})

            traits.append(
                {
                    "internal": {"hash": trait.path, "name": trait.getv("mName")},
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
