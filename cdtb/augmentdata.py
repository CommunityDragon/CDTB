import copy
import logging
import os
from enum import Enum

from .binfile import BinFile
from .rstfile import RstFile
from .storage import PatchVersion
from .tools import convert_cdragon_path, json_dump, stringtable_paths

logger = logging.getLogger(__name__)


class AugmentMode(Enum):
    ARENA = ("arena", ["data", "maps", "shipping", "map30", "map30.bin"])
    ARAM_MAYHEM = ("aram_mayhem", ["maps", "modespecificdata", "kiwi.bin"])

    def __init__(self, lookup_name, augment_data_path):
        self.lookup_name = lookup_name
        self.augment_data_path = augment_data_path


def parse_game_mode(arg):
    val = arg.lower()
    for mode in AugmentMode:
        if mode.lookup_name == val:
            logger.debug(f"Resolving {val} to {mode.name}")
            return mode
    logger.warning(f"Invalid mode: {val}")
    raise ValueError(f"Invalid game_mode specified: {val}. Allowed are {[m.lookup_name for m in AugmentMode]}")


class ArenaTransformer:
    def __init__(self, input_dir, game_mode, game_version=1502):
        self.input_dir = input_dir
        self.game_mode = game_mode
        self.game_version = game_version

    def build_template(self):
        """Parse bin data into template data"""
        map_file = os.path.join(self.input_dir, *self.game_mode.augment_data_path)
        logger.debug(f"Resolving path for {self.game_mode.name} to {map_file}")

        map_file_obj = BinFile(map_file)

        augments = self.parse_augments(map_file_obj)

        return {
            "augments": augments,
        }

    def export(self, output, langs=None):
        """Export Augment data for given languages

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
            replacements = RstFile(stringtables[lang], self.game_version)

            def replace_in_data(entry):
                for key in ("name", "desc", "tooltip"):
                    if key in entry and entry[key] in replacements:
                        entry[key] = replacements[entry[key]]

            for augment in instance["augments"]:
                replace_in_data(augment)

            with open(os.path.join(output, f"{lang}.json"), "w", encoding="utf-8") as f:
                json_dump(instance, f, indent=4, sort_keys=True, ensure_ascii=False)

    def parse_augments(self, map30):
        """Returns a list of augments"""

        augment_entries = [x for x in map30.entries if x.type == "AugmentData"]
        spellobject_entries = {x.path: x for x in map30.entries if x.type == "SpellObject"}

        augments = []
        for augment in augment_entries:
            if not augment.getv("enabled", True):
                continue
            augment_datavalues = {}
            augment_calculations = {}
            augment_spellobject = augment.getv("RootSpell")
            if augment_spellobject:
                augment_spell = spellobject_entries[augment_spellobject].getv('mSpell')
                for datavalue in augment_spell.getv("DataValues", augment_spell.getv('mDataValues', [])):
                    augment_datavalues[datavalue.getv("name", datavalue.getv("mName"))] = datavalue.getv("values",
                                                                                                         datavalue.getv(
                                                                                                             "mValues",
                                                                                                             [0])[0])

                # Giving raw calculations data due to not having a well defined standard
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


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="directory with extracted bin files")
    parser.add_argument("-m", "--game-mode", choices=[m.lookup_name for m in AugmentMode],
                        default=AugmentMode.ARENA.lookup_name, help="Game mode to export")
    parser.add_argument("-o", "--output", default="augments", help="output directory")
    parser.add_argument('-V', '--patch-version', default=None,
                        help="patch version the input files belong to in the format XX.YY (default: latest patch)")
    args = parser.parse_args()

    parsed_version = PatchVersion(args.patch_version if args.patch_version else "main").as_int()
    parsed_mode = parse_game_mode(args.game_mode)

    arena_transformer = ArenaTransformer(args.input, game_mode=parsed_mode, game_version=parsed_version)
    arena_transformer.export(args.output, langs=None)


if __name__ == "__main__":
    main()
