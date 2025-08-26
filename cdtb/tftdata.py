import os
import copy
from .storage import PatchVersion
from .binfile import BinFile, BinEmbedded
from .rstfile import RstFile
from .tools import json_dump, stringtable_paths


def load_translations(path, game_version=1502):
    with open(path, "rb") as f:
        if f.read(3) == b"RST":
            f.seek(0)
            return RstFile(f, game_version)
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

def collect_effects(data):
    """Collect effects from item or trait data"""

    if "effectAmounts" in data:
        return {str(effect.getv("name")): effect.getv("value") for effect in data.getv("effectAmounts")}
    elif "constants" in data:
        return {str(k): v.getv("mValue") for k, v in data.getv("constants").getv(0xdf085b93, {}).items()}
    return {}


class TftTransformer:
    def __init__(self, input_dir, game_version=1502):
        self.input_dir = input_dir
        self.game_version = game_version

    def build_template(self):
        """Parse bin data into template data"""
        map22_file = os.path.join(self.input_dir, "data", "maps", "shipping", "map22", "map22.bin")

        map22 = BinFile(map22_file)

        character_names = self.parse_character_names(map22)
        traits = self.parse_traits(map22)
        sets = self.parse_sets(map22, character_names, traits)
        champs = self.parse_champs(map22, traits)
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

        stringtables = stringtable_paths(self.input_dir, "tft")

        if langs is None:
            langs = list(stringtables)

        os.makedirs(output, exist_ok=True)

        template = self.build_template()
        for lang in langs:
            instance = copy.deepcopy(template)
            replacements = load_translations(stringtables[lang], self.game_version)

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
                json_dump(instance, f, indent=4, sort_keys=True, ensure_ascii=False)

    def build_output_sets(self, sets, champs):
        """Build sets as output in the final JSON file"""

        output_sets = {}
        output_set_data = []
        for set_number, set_mutator, set_name, set_chars, set_traits, set_augments, set_items in sets:
            set_champs_pairs = [champs[name] for name in set_chars if name in champs]
            set_champions = [p[0] for p in set_champs_pairs]
            output_set_data.append({
                "number": set_number,
                "mutator": set_mutator,
                "name": set_name,
                "traits": set_traits,
                "champions": set_champions,
                "augments": set_augments,
                "items": set_items,
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
        return {x.path: x.getv("name").lower() for x in map22.entries if x.type == "Character" or x.type == "TftCharacter"}

    def parse_sets(self, map22, character_names, traits):
        """Parse character sets to a list of `(name, number, characters, traits, augments, items)`"""
        character_lists = {x.path: x for x in map22.entries if x.type == "MapCharacterList" or x.type == "TftCharacterList"}
        trait_lists = {x.path: x for x in map22.entries if x.type == "TftTraitList"}
        set_collection = [x for x in map22.entries if x.type == 0x438850FF]
        item_lists = {x.path: x for x in map22.entries if x.type == "TFTItemList"}
        item_entries = {x.path: x for x in map22.entries if x.type == "TftItemData"}

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
            char_lists = item.getv("characterLists", []) + item.getv("tftCharacterLists", [])
            if not char_lists:
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

            set_augment_ids = set()
            set_items_ids = set()
            for item_list in item.getv("ItemLists", []):
                if item_list not in item_lists:
                    continue
                item_list_entry = item_lists[item_list]
                for item_entry in item_list_entry.getv("mItems", []):
                    if item_entry not in item_entries:
                        continue
                    if item_entries[item_entry].getv("IsAugment"):
                        set_augment_ids.add(item_entries[item_entry].getv("mName"))
                    else:
                        set_items_ids.add(item_entries[item_entry].getv("mName"))
            set_augments = sorted(set_augment_ids)
            set_items = sorted(set_items_ids)

            sets.append((set_number, set_mutator, set_name, set_characters, set_traits, set_augments, set_items))
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
                "effects": collect_effects(item),
                "tags": [str(x) for x in item.getv("ItemTags", [])]
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

    def parse_champs(self, map22, traits):
        """Parse champion information

        Return a map of `(data, traits)`, indexed by champion internal names.
        """
        champ_entries = [x for x in map22.entries if x.type == "TftShopData"]
        champs = {}
        data_characters_dir = os.path.join(self.input_dir, "data", "characters")
        characters_dir = os.path.join(self.input_dir, "characters")
        role_entries = {x.path: x for x in map22.entries if x.type == "TFTCharacterRoleData"}

        for champ in champ_entries:
            # always use lowercased name: required for files, and bin data is inconsistent
            name = champ.getv("mName").lower()
            if name == "tft_template":
                continue

            self_path = os.path.join(characters_dir, name + ".cdtb.bin")
            if not os.path.exists(self_path):
                self_path = os.path.join(data_characters_dir, name, name + ".bin")
            if not os.path.exists(self_path):
                continue

            tft_bin = BinFile(self_path)
            record = next((x for x in tft_bin.entries if x.type == "TFTCharacterRecord"), {})
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
            spell_key_name = None
            spell_key_tooltip = None
            for entry in tft_bin.entries:
                if entry.type == "SpellObject" and entry.getv("mScriptName").lower() == spell_name:
                    ability = entry.getv("mSpell")
                    ability_variables = [{"name": value.getv("mName"), "value": value.getv("mValues")} for value in ability.getv("DataValues", ability.getv("mDataValues", []))]
                    if loc_keys := ability.get_path("mClientData", "mTooltipData", "mLocKeys"):
                        spell_key_name = loc_keys.get("keyName")
                        spell_key_tooltip = loc_keys.get("keyTooltip")
                    break
            else:
                ability_variables = []

            cost = record.getv("tier", None)
            if cost is None:
                rarity = champ.getv("mRarity", 0) + 1
                cost = rarity + int(rarity / 6)

            role_key = record.getv("CharacterRole")
            role = role_entries[role_key].getv("name") if role_key is not None else None
            ability_resource_info = record.getv("primaryAbilityResource")
            mana = ability_resource_info.getv("arBase", 100) if ability_resource_info is not None else 100

            champs[name] = ({
                "apiName": champ.getv("mName"),
                "characterName": record.getv("mCharacterName"),
                "name": champ.getv(0xC3143D66),
                "cost": cost,
                "icon": champ.getv(0x466DC3CC) or champ.getv("mIconPath"),
                "tileIcon": champ.getv(0xDAC11DD4),
                "squareIcon": champ.getv(0x16071366),
                "traits": [traits[h]["name"] for h in champ_traits if h in traits],
                "role": role,
                "stats": {
                    "hp": record.getv("baseHP"),
                    "mana": mana,
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
                    "name": champ.getv(0x87A69A5E) or spell_key_name,
                    "desc": champ.getv(0xBC4F18B3) or spell_key_tooltip,
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

            base_effects = {}
            for trait_set in trait.getv(0x6f4cf34d, []):
                base_effects |= collect_effects(trait_set)

            effects = []
            if "mTraitSets" in trait:
                trait_sets = trait.getv("mTraitSets")
                field_prefix = 'm'
            else:
                trait_sets = trait.getv("mConditionalTraitSets", [])
                field_prefix = ''
            for trait_set in trait_sets:
                effects.append({
                    "minUnits": trait_set.getv(field_prefix + "MinUnits"),
                    "maxUnits": trait_set.getv(field_prefix + "MaxUnits") or 25000,
                    "style": trait_set.getv(field_prefix + "Style", 1),
                    "variables": base_effects | collect_effects(trait_set),
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
    parser.add_argument('-V', '--patch-version', default=None,
                           help="patch version the input files belong to in the format XX.YY (default: latest patch)")
    args = parser.parse_args()

    parsed_version = PatchVersion(args.patch_version if args.patch_version else "main").as_int()

    tft_transformer = TftTransformer(args.input, game_version=parsed_version)
    tft_transformer.export(args.output, langs=None)

if __name__ == "__main__":
    main()
