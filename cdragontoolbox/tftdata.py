import json
import glob
import os
import copy
import re
from .binfile import BinFile, BinHashBase, BinEmbedded
from .rstfile import RstFile


class NaiveJsonEncoder(json.JSONEncoder):
    def default(self, other):
        if isinstance(other, BinHashBase):
            if other.s is None:
                return other.hex()
            return other.s
        return other.__dict__

def load_translations(path):
    with open(path, "rb") as f:
        if f.read(3) == b"RST":
            f.seek(0)
            return RstFile(f)
        else:
            translations = {}
            for line in f:
                if line.startswith(b'tr "'):
                    line = line.decode()
                    key, val = line.split("=", 1)
                    key = key[4:-2]
                    val = val[2:-2]
                    translations[key] = val
            return translations


class TftTransformer:
    def __init__(self, input_dir):
        self.input_dir = input_dir

    def build_template(self):
        """Parse bin data into template data"""
        map22_file = os.path.join(self.input_dir, "data", "maps", "shipping", "map22", "map22.bin")
        character_folder = os.path.join(self.input_dir, "data", "characters")

        map22 = BinFile(map22_file)

        character_names = self.parse_character_names(map22)
        traits = self.parse_traits(map22)
        sets = self.parse_sets(map22, character_names, traits)
        champs = self.parse_champs(map22, traits, character_folder)
        output_sets, output_set_data = self.build_output_sets(sets, champs)
        items = self.parse_items(map22)

        return {
            "sets": output_sets,
            "setData": output_set_data,
            "items": items,
        }

    def export(self, output, langs=None):
        """Export TFT data for given languages

        By default (`langs` is `None`), export all available languages.
        Otherwise, export for given `xx_yy` language codes.
        """

        stringtable_dir = os.path.join(self.input_dir, "data/menu")
        # Support both 'font_config_*.txt' (old) and 'main_*.stringtable' (new)
        if os.path.exists(os.path.join(stringtable_dir, "fontconfig_en_us.txt")):
            stringtable_glob = "fontconfig_??_??.txt"
            stringtable_format = "fontconfig_%s.txt"
            stringtable_regex = r"fontconfig_(.._..)\.txt$"
        else:
            stringtable_glob = "main_??_??.stringtable"
            stringtable_format = "main_%s.stringtable"
            stringtable_regex = r"main_(.._..)\.stringtable$"


        if langs is None:
            langs = []
            for path in glob.glob(os.path.join(stringtable_dir, stringtable_glob)):
                m = re.search(stringtable_regex, path)
                if m:
                    langs.append(m.group(1))

        os.makedirs(output, exist_ok=True)

        template = self.build_template()
        for lang in langs:
            instance = copy.deepcopy(template)
            replacements = load_translations(os.path.join(stringtable_dir, stringtable_format % lang))

            def replace_in_data(entry):
                for key in ("name", "desc"):
                    if key in entry and entry[key] in replacements:
                        entry[key] = replacements[entry[key]]
            def replace_list(l):
                l[:] = [replacements.get(v, v) for v in l]

            def replace_set_data(entry):
                for trait_data in entry["traits"]:
                    replace_in_data(trait_data)
                for champ_data in entry["champions"]:
                    replace_in_data(champ_data)
                    replace_list(champ_data["traits"])
                    if "ability" in champ_data:
                        replace_in_data(champ_data["ability"])

            for set_data in instance["sets"].values():
                replace_set_data(set_data)
            for set_data in instance["setData"]:
                replace_set_data(set_data)
            for data in instance["items"]:
                replace_in_data(data)

            with open(os.path.join(output, f"{lang}.json"), "w", encoding="utf-8") as f:
                json.dump(instance, f, cls=NaiveJsonEncoder, indent=4, sort_keys=True)

    def build_output_sets(self, sets, champs):
        """Build sets as output in the final JSON file"""

        output_sets = {}
        output_set_data = []
        for set_number, set_mutator, set_name, set_chars, set_traits in sets:
            set_champs_pairs = [champs[name] for name in set_chars if name in champs]
            set_champions = [p[0] for p in set_champs_pairs]
            output_set_data.append({
                "number": set_number,
                "mutator": set_mutator,
                "name": set_name,
                "traits": set_traits,
                "champions": set_champions,
            })
            output_sets[set_number] = {
                "name": set_name,
                "traits": set_traits,
                "champions": set_champions,
            }
        return output_sets, output_set_data

    def parse_character_names(self, map22):
        """Parse character names, indexed by entry path"""
        # always use lowercased name: required for files, and bin data is inconsistent
        return {x.path: x.getv("name").lower() for x in map22.entries if x.type == "Character"}

    def parse_sets(self, map22, character_names, traits):
        """Parse character sets to a list of `(name, number, characters, traits)`"""
        character_lists = {x.path: x for x in map22.entries if x.type == "MapCharacterList"}
        trait_lists = {x.path: x for x in map22.entries if x.type == "TftTraitList"}
        set_collection = [x for x in map22.entries if x.type == 0x438850FF]

        if not set_collection:
            # backward compatibility
            longest_character_list = max(character_lists.values(), key=lambda v: len(v.fields[0].value))
            longest_trait_list = max(trait_lists.values(), key=lambda v: len(v.fields[0].value))
            champion_list = longest_character_list.fields[0].value
            trait_list = longest_trait_list.fields[0].value
            set_characters = [character_names.get(char) for char in champion_list]
            set_traits = [traits.get(trait) for trait in trait_list]
            return [(1, "Base", set_characters, set_traits)]

        sets = []
        for item in set_collection:
            set_number = item.getv("number")
            set_mutator = item.getv("Mutator")
            if set_mutator is None:
                set_mutator = item.getv("name")
            char_lists = item.getv("characterLists")
            if char_lists is None:
                continue
            set_trait_lists = item.getv("TraitLists")
            if set_trait_lists is None:
                continue
            set_info = item[0xD2538E5A].value
            set_name = set_info["SetName"].getv("mValue")

            if set_number is None or set_name is None:
                continue
            set_characters = []
            for char_list in char_lists:
                if char_list not in character_lists:
                    continue
                set_characters += [character_names[char] for char in character_lists[char_list].getv("Characters") if char in character_names]

            set_trait_paths = []
            for trait_list in set_trait_lists:
                if trait_list not in trait_lists:
                    continue
                set_trait_paths += trait_lists[trait_list].getv("mTraits")
            set_traits = [traits[path] for path in set(set_trait_paths) if path in traits]

            sets.append((set_number, set_mutator, set_name, set_characters, set_traits))
        return sets

    def parse_items(self, map22):
        item_entries = [x for x in map22.entries if x.type == "TftItemData"]
        trait_entries = [x for x in map22.entries if x.type == "TftTraitData"]

        traits_by_hash = {trait.path.h: trait.getv("mName") for trait in trait_entries}

        items = []
        items_by_hash = {}  # {item_hash: item}
        for item in item_entries:
            name = item.getv("mName")
            if "Template" in name or name == "TFT_Item_Null":
                continue

            effects = {}
            for effect in item.getv("effectAmounts", []):
                name = str(effect.getv("name")) if "name" in effect else effect.path.hex()
                effects[name] = effect.getv("value", "null")

            item_data = {
                "id": item.getv("mId"),
                "name": item.getv(0xC3143D66),
                "apiName": item.getv("mName"),
                "desc": item.getv(0x765F18DA),
                "icon": item.getv("mIconPath"),
                "unique": item.getv(0x9596A387, False),
                "composition": [x.h for x in item.getv(0x8B83BA8A, [])],  # updated below
                "associatedTraits": [x.h for x in item.getv("AssociatedTraits", [])], # updated below
                "incompatibleTraits": [x.h for x in item.getv("IncompatibleTraits", [])], # updated below
                "effects": effects,
            }
            items.append(item_data)
            items_by_hash[item.path.h] = item_data


        for item in items:
            if item["id"] is not None:
                # patchs < 13.5: mId exist and "from" is a list of those IDs
                item["from"] = [items_by_hash[h]["id"] for h in item["composition"]]
            else:
                item["from"] = None
            item["composition"] = [items_by_hash[h]["apiName"] for h in item["composition"]]
            item["incompatibleTraits"] = [traits_by_hash[h] for h in item["incompatibleTraits"]]
            item["associatedTraits"] = [traits_by_hash[h] for h in item["associatedTraits"]]
        return items

    def parse_champs(self, map22, traits, character_folder):
        """Parse champion information

        Return a map of `(data, traits)`, indexed by champion internal names.
        """
        champ_entries = [x for x in map22.entries if x.type == "TftShopData"]
        champs = {}

        for champ in champ_entries:
            # always use lowercased name: required for files, and bin data is inconsistent
            name = champ.getv("mName").lower()
            if name == "tft_template":
                continue

            self_path = os.path.join(character_folder, name, name + ".bin")
            if not os.path.exists(self_path):
                continue

            tft_bin = BinFile(self_path)
            record = next(x for x in tft_bin.entries if x.type == "TFTCharacterRecord")
            if "spellNames" not in record:
                continue

            champ_traits = []  # trait paths, as hashes
            for trait in record.getv("mLinkedTraits", []):
                if isinstance(trait, BinEmbedded):
                    champ_traits.extend(field.value for field in trait.fields if field.name.h == 0x053A1F33)
                else:
                    champ_traits.append(trait.h)

            spell_name = record.getv("spellNames")[0]
            spell_name = spell_name.rsplit("/", 1)[-1].lower()
            for entry in tft_bin.entries:
                if entry.type == "SpellObject" and entry.getv("mScriptName").lower() == spell_name:
                    ability = entry.getv("mSpell")
                    ability_variables = [{"name": value.getv("mName"), "value": value.getv("mValues")} for value in ability.getv("mDataValues", [])]
                    break
            else:
                ability_variables = []

            cost = record.getv("tier", None)
            if cost is None:
                rarity = champ.getv("mRarity", 0) + 1
                cost = rarity + int(rarity / 6)

            champs[name] = ({
                "apiName": champ.getv("mName"),
                "characterName": record.getv("mCharacterName"),
                "name": champ.getv(0xC3143D66),
                "cost": cost,
                "icon": champ.getv(0x466DC3CC) or champ.getv("mIconPath"),
                "tileIcon": champ.getv(0xDAC11DD4),
                "squareIcon": champ.getv(0x16071366),
                "traits": [traits[h]["name"] for h in champ_traits if h in traits],
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
                    "range": record.getv("attackRange", 0) // 180,
                },
                "ability": {
                    "name": champ.getv(0x87A69A5E),
                    "desc": champ.getv(0xBC4F18B3),
                    "icon": champ.getv(0xDF0AD83B) or champ.getv("mPortraitIconPath"),
                    "variables": ability_variables,
                },
            }, champ_traits)

        return champs

    def parse_traits(self, map22):
        """Parse traits, return a map indexed by entry path"""
        trait_entries = [x for x in map22.entries if x.type == "TftTraitData"]

        traits = {}
        for trait in trait_entries:
            if "Template" in trait.getv("mName"):
                continue

            effects = []
            if "mTraitSets" in trait:
                trait_sets = trait.getv("mTraitSets")
                field_prefix = 'm'
            else:
                trait_sets = trait.getv(0x93dd1f25)
                field_prefix = ''
            for trait_set in trait_sets:
                variables = {}
                for effect in trait_set.getv("effectAmounts", []):
                    name = str(effect.getv("name")) if "name" in effect else "null"
                    variables[name] = effect.getv("value", "null")

                effects.append({
                    "minUnits": trait_set.getv(field_prefix + "MinUnits"),
                    "maxUnits": trait_set.getv(field_prefix + "MaxUnits") or 25000,
                    "style": trait_set.getv(field_prefix + "Style", 1),
                    "variables": variables,
                })

            traits[trait.path] = {
                "apiName": trait.getv("mName"),
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
