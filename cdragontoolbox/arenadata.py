import json
import glob
import os
import copy
import re
from .binfile import BinFile, BinHashBase
from .rstfile import RstFile


class NaiveJsonEncoder(json.JSONEncoder):
    def default(self, other):
        if isinstance(other, BinHashBase):
            if other.s is None:
                return other.hex()
            return other.s
        return other.__dict__


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
            replacements = RstFile(os.path.join(stringtable_dir, stringtable_format % lang))

            def replace_in_data(entry):
                for key in ("name", "desc", "tooltip"):
                    if key in entry and entry[key] in replacements:
                        entry[key] = replacements[entry[key]]

            for augment in instance["augments"]:
                replace_in_data(augment)

            with open(os.path.join(output, f"{lang}.json"), "w", encoding="utf-8") as f:
                json.dump(instance, f, cls=NaiveJsonEncoder, indent=4, sort_keys=True)

    def parse_augments(self, map30):
        """Returns a list of augments"""
        augment_entries = [x for x in map30.entries if x.type == 0x6DFAB860]
        spellobject_entries = {x.path: x for x in map30.entries if x.type == "SpellObject"}

        augments = []
        for augment in augment_entries:
            if not augment.getv("enabled", True):
                continue
            augment_datavalues = {}
            augment_calculations = {}
            augment_spellobject = augment.getv(0x1418F849)
            if augment_spellobject:
                augment_spell = spellobject_entries[augment_spellobject].getv('mSpell')
                for datavalue in augment_spell.getv('mDataValues', []):
                    augment_datavalues[datavalue.getv("mName")] = datavalue.getv("mValues", [0])[0]

                #Giving raw calculations data due to not having a well defined standard
                if augment_spell.get('mSpellCalculations'):
                    augment_calculations = augment_spell.get('mSpellCalculations').to_serializable()[1]

            augments.append({
                "id": augment.getv(0x827DC19E),
                "apiName": augment.getv(0x19AE3E16),
                "name": augment.getv(0x2127EB37),
                "desc": augment.getv("DescriptionTra"),
                "tooltip": augment.getv(0x366935FC),
                "iconSmall": convert_cdragon_path(augment.getv(0x45481FB5)),
                "iconLarge": convert_cdragon_path(augment.getv(0xF1F7E50D)),
                "rarity": augment.getv("rarity", 0),
                "dataValues": augment_datavalues,
                "calculations": augment_calculations,
            })

        return augments

def convert_cdragon_path(path):
    return path.lower().replace(".dds", ".png").replace(".tex", ".png")

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
