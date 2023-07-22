import json
import glob
import os
import copy
import re
from .binfile import BinFile
from .tftdata import NaiveJsonEncoder, load_translations


class ArenaTransformer:
    def __init__(self, input_dir):
        self.input_dir = input_dir

    def build_template(self):
        """Parse bin data into template data"""
        map30_file = os.path.join(self.input_dir, "data", "maps", "shipping", "map30", "map30.bin")

        map30 = BinFile(map30_file)

        augments = self.parse_augments(map30)

        return {
            "augments": augments,
        }

    def export(self, output, langs=None):
        """Export Arena data for given languages

        By default (`langs` is `None`), export all available languages.
        Otherwise, export for given `xx_yy` language codes.
        """

        stringtable_dir = os.path.join(self.input_dir, "data/menu")
        # Support both 'font_config_*.txt' (old) and 'main_*.stringtable' (new)
        if os.path.exists(os.path.join(stringtable_dir, "fontconfig_en_us.txt")):
            stringtable_pattern = "fontconfig_??_??.txt"
            stringtable_format = "fontconfig_%s.txt"
        else:
            stringtable_pattern = "main_??_??.stringtable"
            stringtable_format = "main_%s.stringtable"

        if langs is None:
            langs = []
            for path in glob.glob(os.path.join(stringtable_dir, stringtable_pattern)):
                # Note: must be adjusted if format changes
                m = re.search(r'/\w*_(.._..)\.\w*$', path)
                if m:
                    langs.append(m.group(1))

        os.makedirs(output, exist_ok=True)

        template = self.build_template()
        for lang in langs:
            instance = copy.deepcopy(template)
            replacements = load_translations(os.path.join(stringtable_dir, stringtable_format % lang))

            def replace_in_data(entry):
                for key in ("name", "desc", "tooltip"):
                    if key in entry and entry[key] in replacements:
                        entry[key] = replacements[entry[key]]

            for augment in instance["augments"]:
                replace_in_data(augment)

            with open(os.path.join(output, f"{lang}.json"), "w", encoding="utf-8") as f:
                json.dump(instance, f, cls=NaiveJsonEncoder, indent=4, sort_keys=True)

    def parse_augments(self, map30):
        """Returns a list of augments sorted by numerical id"""
        augment_entries = [x for x in map30.entries if x.type == 0x6DFAB860]
        spellobject_entries = {str(x.path): x for x in map30.entries if x.type == "SpellObject"}

        augments = []
        for augment in augment_entries:

            augment_datavalues = {}
            if augment.getv(0x1418F849):
                try:
                    for datavalue in spellobject_entries[str(augment.getv(0x1418F849))].getv('mSpell').getv('mDataValues'):
                        augment_datavalues[datavalue.getv("mName")] = datavalue.getv("mValues")[0]
                except TypeError:
                    pass

                #Giving raw calculations data due to not having a well defined standard
                augment_calculations = {}
                try:
                    augment_calculations.update(
                        spellobject_entries[str(augment.getv(0x1418F849))].getv('mSpell').get('mSpellCalculations').to_serializable()[1]
                    )
                except AttributeError:
                    pass
            

            augments.append({
                "id": augment.getv(0x827DC19E),
                "apiName": augment.getv(0x19AE3E16),
                "name": augment.getv(0x2127EB37),
                "desc": augment.getv("DescriptionTra"),
                "tooltip": augment.getv(0x366935FC),
                "iconSmall": augment.getv(0x45481FB5),
                "iconLarge": augment.getv(0xF1F7E50D),
                "rarity": augment.getv("rarity") or 0,
                "datavalues": augment_datavalues,
                "calculations": augment_calculations,
            })

        augments.sort(key=lambda x:x['id'])
        return augments


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="directory with extracted bin files")
    parser.add_argument("-o", "--output", default="arena", help="output directory")
    args = parser.parse_args()

    arena_transformer = ArenaTransformer(args.input)
    arena_transformer.export(args.output, langs=None)

if __name__ == "__main__":
    main()
