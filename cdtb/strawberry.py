import os
import copy
import json
from .storage import PatchVersion
from .binfile import BinFile
from .rstfile import RstFile
from .tools import convert_cdragon_path, json_dump, stringtable_paths

class StrawBerryTransformer:
    def __init__(self, input_dir, game_version=1415):
        self.input_dir = input_dir
        self.rsthash_version = game_version

    def build_template(self):
        """Parse bin data into template data"""
        map33_file = os.path.join(self.input_dir, "data", "maps", "shipping", "map33", "map33.bin")

        map33 = BinFile(map33_file)

        augments = self.parse_augments(map33)

        return {
            "augments": augments,
        }

    def export(self, output, langs=None):
        """Export StrawBerry data for given languages

        By default (`langs` is `None`), export all available languages.
        Otherwise, export for given `xx_yy` language codes.
        """

        stringtables = stringtable_paths(self.input_dir, "lol")
        if langs is None:
            langs = list(stringtables)

        os.makedirs(output, exist_ok=True)

        template = self.build_template()
        for lang in langs:
            instance = copy.deepcopy(template)
            replacements = RstFile(stringtables[lang], self.rsthash_version)

            def replace_in_data(entry):
                for key in ("name", "desc", "tooltip"):
                    if key in entry and entry[key] in replacements:
                        entry[key] = replacements[entry[key]]

            for augment in instance["augments"]:
                replace_in_data(augment)

            with open(os.path.join(output, f"{lang}.json"), "w", encoding="utf-8") as f:
                try:
                    json.dump(instance, f, separators=(',', ':'), ensure_ascii=False, default=str)
                except TypeError as e:
                    print(f"Error serializing JSON for language {lang}: {e}")

    def parse_augments(self, map33):
        """Returns a list of augments"""
        augment_entries = [x for x in map33.entries if x.type == 0x6DFAB860]
        spellobject_entries = {x.path: x for x in map33.entries if x.type == "SpellObject"}

        augments = []
        for augment in augment_entries:
            augment_datavalues = {}
            augment_calculations = {}
            augment_spellobject_path = augment.getv(0x1418F849)

            if augment_spellobject_path:
                augment_spellobject = spellobject_entries.get(augment_spellobject_path)
                if augment_spellobject:
                    augment_spell = augment_spellobject.getv('mSpell')

                    # DataValues
                    for datavalue in augment_spell.getv('mDataValues', []):
                        name = datavalue.getv("mName")
                        values = datavalue.getv("mValues", [])
                        if name:
                            # One lane
                            augment_datavalues[name] = values

                    # Calculations
                    if augment_spell.get('mSpellCalculations'):
                        try:
                            calculations = augment_spell.get('mSpellCalculations').to_serializable()[1]
                            for key, calc in calculations.items():
                                formula_parts = calc.get("mFormulaParts", [])
                                calculation_summary = [part.get("mDataValue") for part in formula_parts if part.get("mDataValue")]
                                augment_calculations[key] = calculation_summary
                        except Exception as e:
                            print(f"Error serializing mSpellCalculations: {e}")

            augments.append({
                "id": augment.getv(0x827DC19E),
                "apiName": augment.getv(0x19AE3E16),
                "dataValues": augment_datavalues,
                "calculations": augment_calculations,
                "name": augment.getv(0x2127EB37),
                "desc": augment.getv("DescriptionTra"),
                "tooltip": augment.getv(0x366935FC),
                "iconSmall": convert_cdragon_path(augment.getv(0x45481FB5)),
                "iconLarge": convert_cdragon_path(augment.getv(0xF1F7E50D)),
                "rarity": augment.getv("rarity", 0),
            })

        return augments

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="directory with extracted bin files")
    parser.add_argument("-o", "--output", default="arena", help="output directory")
    parser.add_argument('-V', '--patch-version', default=None,
                           help="patch version the input files belong to in the format XX.YY (default: latest patch)")
    args = parser.parse_args()

    parsed_version = PatchVersion(args.patch_version if args.patch_version else "main").as_int()

    strawberry_transformer = StrawBerryTransformer(args.input, game_version=parsed_version)
    strawberry_transformer.export(args.output, langs=None)

if __name__ == "__main__":
    main()
