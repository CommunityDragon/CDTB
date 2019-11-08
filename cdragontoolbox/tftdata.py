import json
import glob
import os
import copy
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

        character_names = self.parse_character_names(map22)
        sets = self.parse_sets(map22, character_names)
        traits = self.parse_traits(map22)
        champs = self.parse_champs(map22, traits, character_folder)
        output_sets = self.build_output_sets(sets, traits, champs)
        items = self.parse_items(map22)

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
            def replace_list(l):
                l[:] = [replacements.get(v, v) for v in l]

            for set_data in instance["sets"].values():
                for trait_data in set_data["traits"]:
                    replace_in_data(trait_data)
                for champ_data in set_data["champions"]:
                    replace_in_data(champ_data)
                    replace_list(champ_data["traits"])
                    if "ability" in champ_data:
                        replace_in_data(champ_data["ability"])
            for data in instance["items"]:
                replace_in_data(data)

            with open(os.path.join(output, f"{lang}.json"), "w", encoding="utf-8") as f:
                json.dump(instance, f, cls=NaiveJsonEncoder, indent=4, sort_keys=True)

    def build_output_sets(self, sets, traits, champs):
        """Build sets as output in the final JSON file"""

        traits_by_name = {trait["name"]: trait for trait in traits.values()}

        set_map = {}
        for set_number, set_name, set_chars in sets:
            set_champs = [champs[name] for name in set_chars if name in champs]
            if len(sets) > 1:
                set_traits_names = {trait for champ in set_champs for trait in champ["traits"]}
                set_traits = [traits_by_name[t] for t in set_traits_names]
            else:
                # backward compatibility
                set_traits = list(traits.values())

            set_map[set_number] = {
                "name": set_name,
                "traits": set_traits,
                "champions": set_champs,
            }
        return set_map

    def parse_character_names(self, map22):
        """Parse character names, indexed by entry path"""
        return {x.path: x.getv("name") for x in map22.entries if x.type == "Character"}

    def parse_sets(self, map22, character_names):
        """Parse character sets to a list of `(name, number, characters)`"""
        character_lists = {x.path: x for x in map22.entries if x.type == "MapCharacterList"}
        set_collection = [x for x in map22.entries if x.type == 0x438850FF]

        if not set_collection:
            # backward compatibility
            longest_character_list = max(character_lists.values(), key=lambda v: len(v.fields[0].value))
            champion_list = longest_character_list.fields[0].value
            set_characters = [character_names.get(char) for char in champion_list]
            return [(1, "Base", set_characters)]

        sets = []
        for item in set_collection:
            char_list = item.getv("characterLists")[0]
            set_info = item[0xD2538E5A].value
            set_number = set_info["SetNumber"]["mValue"].value
            set_name = set_info["SetName"]["mValue"].value

            if char_list not in character_lists:
                continue

            set_characters = [character_names[char] for char in character_lists[char_list].getv("Characters")]
            sets.append((set_number, set_name, set_characters))
        return sets

    def parse_items(self, map22):
        item_entries = [x for x in map22.entries if x.type == "TftItemData"]

        items = []
        item_ids = {}  # {item_hash: item_id}
        for item in item_entries:
            name = item.getv("mName")
            if "Template" in name or name == "TFT_Item_Null":
                continue

            effects = {}
            for effect in item.getv("effectAmounts", []):
                name = str(effect.getv("name")) if "name" in effect else effect.path.hex()
                effects[name] = effect.getv("value", "null")

            items.append({
                "id": item.getv("mId"),
                "name": item.getv(0xC3143D66),
                "desc": item.getv(0x765F18DA),
                "icon": item.getv("mIconPath"),
                "from": [x.h for x in item.getv(0x8B83BA8A, [])],
                "effects": effects,
            })
            item_ids[item.path.h] = item.getv("mId")

        for item in items:
            item["from"] = [item_ids[x] for x in item["from"]]

        return items

    @staticmethod
    def find_closest_path(parent, name):
        while name:
            path = os.path.join(parent, name, name + ".bin")
            if os.path.exists(path):
                return path
            name = name[:-1]
        return None

    def parse_champs(self, map22, traits, character_folder):
        """Parse champion information, return a map indexed by their internal name"""
        champ_entries = [x for x in map22.entries if x.type == "TftShopData"]
        champs = {}

        for champ in champ_entries:
            name = champ.getv("mName")
            if name == "TFT_Template":
                continue
            lname = name.lower()

            self_path = os.path.join(character_folder, lname, lname + ".bin")
            if not os.path.exists(self_path):
                continue

            closest_path = self.find_closest_path(character_folder, lname.split("_", 1)[-1])
            char_bin = BinFile(closest_path)
            champ_id = next(x["characterToolData"].value.getv("championId") for x in char_bin.entries if x.type == "CharacterRecord")

            tft_bin = BinFile(self_path)
            record = next(x for x in tft_bin.entries if x.type == "TFTCharacterRecord")

            champ_traits = []  # trait paths, as hashes
            for trait in record.getv("mLinkedTraits", []):
                if isinstance(trait, BinEmbedded):
                    champ_traits.extend(field.value for field in trait.fields if field.name.h == 0x053A1F33)
                else:
                    champ_traits.append(trait.h)
            # convert trait hashes to names
            champ_traits = [traits[h]["name"] for h in champ_traits]

            spell_name = record.getv("spellNames")[0]
            spell_name = spell_name.rsplit("/", 1)[-1]
            ability = next(x.getv("mSpell") for x in tft_bin.entries if x.type == "SpellObject" and x.getv("mScriptName") == spell_name)
            ability_variables = [{"name": value.getv("mName"), "value": value.getv("mValues")} for value in ability["mDataValues"].value]
            rarity = champ.getv("mRarity", 0) + 1

            champs[name] = {
                "id": champ_id,
                "name": champ.getv(0xC3143D66),
                "cost": rarity + int(rarity / 6),
                "icon": champ.getv("mIconPath"),
                "traits": champ_traits,
                "stats": {
                    "hp": record.getv("baseHP"),
                    "mana": record["primaryAbilityResource"].value.getv("arBase", 100),
                    "initialMana": record.getv("mInitialMana", 0),
                    "damage": record.getv("BaseDamage"),
                    "armor": record.getv("baseArmor"),
                    "magicResist": record.getv("baseSpellBlock"),
                    "critMultiplier": record.getv("critDamageMultiplier"),
                    "critChance": record.getv("baseCritChance"),
                    "attackSpeed": record.getv("attackSpeed"),
                    "range": record["attackRange"].value // 180,
                },
                "ability": {
                    "name": champ.getv(0x87A69A5E),
                    "desc": champ.getv(0xBC4F18B3),
                    "icon": champ.getv("mPortraitIconPath"),
                    "variables": ability_variables,
                },
            }

        return champs

    def parse_traits(self, map22):
        """Parse traits, return a map indexed by entry path"""
        trait_entries = [x for x in map22.entries if x.type == "TftTraitData"]

        traits = {}
        for trait in trait_entries:
            if "Template" in trait.getv("mName"):
                continue

            effects = []
            for trait_set in trait.getv("mTraitSets"):
                variables = {}
                for effect in trait_set.getv("effectAmounts", []):
                    name = str(effect.getv("name")) if "name" in effect else "null"
                    variables[name] = effect.getv("value", "null")

                effects.append({
                    "minUnits": trait_set.getv("mMinUnits"),
                    "maxUnits": trait_set.getv("mMaxUnits") or 25000,
                    "variables": variables,
                })

            traits[trait.path] = {
                "name": trait.getv(0xC3143D66),
                "desc": trait.getv(0x765F18DA),
                "icon": trait.getv("mIconPath"),
                "effects": effects,
            }

        return traits


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="directory with extracted bin files")
    parser.add_argument("-o", "--output", default="tft", help="output directory")
    args = parser.parse_args()

    tft_transformer = TftTransformer(args.input)
    tft_transformer.export(args.output, langs=None)

if __name__ == "__main__":
    main()

