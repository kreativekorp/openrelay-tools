# Open Relay Tools
Miscellaneous tools for building and modifying fonts.

## Modifying FontForge Source Files
The tool `sfdpatch.py` modifies FontForge .sfd files. For example:

Sort glyphs by code point:

    python tools/sfdpatch.py input.sfd -s > output.sfd

Remove characters:

    python tools/sfdpatch.py input.sfd -r 'uniF000 uniF001 uniF002 uF0000' > output.sfd

Remove all characters not the width of a space:

    python tools/sfdpatch.py input.sfd -m > output.sfd

## Modifying TrueType Font Files
The tool `ttfhack.py` modifies TrueType .ttf files. For example:

Changing ascent and descent:

    python tools/ttfhack.py if=input.ttf winAscent=800 winDescent=200 of=output.ttf

Changing xHeight and capHeight:

    python tools/ttfhack.py if=input.ttf xHeight=500 capHeight=700 of=output.ttf

Changing the top and bottom of the bounding box:

    python tools/ttfhack.py if=input.ttf yMax=1308 yMin=-544 of=output.ttf

## Unicode Character Data & Private Use Area Assignments
The tool `pullucd.py` will download Unicode Character Database files from unicode.org, either the latest version:

    python tools/pullucd.py --latest -d myunicodedata

Or a specific version:

    python tools/pullucd.py -v 16.0.0 -d unicodedata16

The tools `blocks.py` and `unicodedata.py` create equivalent data files for characters in the Private Use Area. For example:

    python tools/blocks.py --tengwar --cirth > Blocks.txt
    python tools/unicodedata.py --tengwar --cirth > UnicodeData.txt

These tools look in the directory `unicodedata` for data files matching flags like `--tengwar` or `--cirth` in the above example. You can also specify data files outside of this directory:

    python tools/blocks.py --tengwar --cirth ./mydata/applebanana.txt > Blocks.txt
    python tools/unicodedata.py --tengwar --cirth ./mydata/applebanana.txt > UnicodeData.txt

The tool `puaabook.py` can use these files to create HTML documentation for the Private Use Area of your font:

    python tools/puaabook.py -D Blocks.txt UnicodeData.txt -I myfont.ttf -O pua.html

The tool `pypuaa.py` can use these files to create a `PUAA` table in your font containing this data:

    python tools/pypuaa.py -D Blocks.txt UnicodeData.txt -I myfont.ttf

See [the `PUAA` table](https://github.com/kreativekorp/bitsnpicas/wiki/The-'PUAA'-table) in the Bits'n'Picas wiki for information about this table. It's currently only used by [Bits'n'Picas](https://github.com/kreativekorp/bitsnpicas) and [PushChar](https://github.com/kreativekorp/pushchar).

### Creating New Private Use Area Data Files
Say you have a set of characters for your conscript Applebanana at FAB00..FAB3F and you want to create a private use area data file for it. Your file will be named `ud0fab00-applebanana.txt` and contain:

    @flag --applebanana
    @file Blocks.txt
    FAB00..FAB3F; Applebanana
    @file UnicodeData.txt
    FAB00;APPLEBANANA CAPITAL LETTER APPLE;Lu;0;L;;;;;N;;;;FAB20;
    FAB01;APPLEBANANA CAPITAL LETTER BANANA;Lu;0;L;;;;;N;;;;FAB21;
    ...
    FAB20;APPLEBANANA SMALL LETTER APPLE;Ll;0;L;;;;;N;;;FAB00;;FAB00
    FAB21;APPLEBANANA SMALL LETTER BANANA;Ll;0;L;;;;;N;;;FAB01;;FAB01
    ...

Please reference [UAX #44 Unicode Character Database](https://www.unicode.org/reports/tr44/) for the syntax of character property files.

You may issue pull requests to this repository to add your own private use area assignments, however:

* Please limit the number of changed files in a pull request to two or three files at most. The more files there are the harder it is to review the pull request.
* Inclusion in this repository does not indicate endorsement or inclusion in any registry maintained elsewhere. **This is not the place to propose new scripts or characters for CSUR, UCSUR, MUFI, SMuFL, or any other private use area agreement.** If that is your goal, please contact the maintainers of the respective registry. For UCSUR, please look for the About link at the bottom of the page. :)
* Do not submit new data files without any character data. If you don't know how you're going to use your block of code points, it's not ready to be in a public repository. Do not speculate about future usage of code space; just because there is a data file for Tengwar Presentation Forms at FE000..FE07F does not mean there will ever be a "Cirth Presentation Forms" at FE080..FE0FF.
* Do not include a `@substring` line in any new data files. This directive and the syntax for `blocks.py` and `unicodedata.py` which uses it is deprecated.
