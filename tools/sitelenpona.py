#!/usr/bin/env python

from __future__ import print_function
from psname import psName, psNames, psUnicode
import re
import sys

class AsukiLine:
	def __init__(self, index, line):
		self.index = index
		fields = line.split('#', 1)
		self.comment = fields[1].strip() if len(fields) > 1 else None
		fields = re.split(r'\s+', fields[0].strip(), 1)
		self.outputPsName = fields[0]
		self.inputPsNames = psNames(fields[1])
		self.sortKey = (-len(self.inputPsNames), fields[1])
		rule = 'sub %s by %s;' % (' '.join(self.inputPsNames), self.outputPsName)
		self.subRule = rule if self.comment is None else '%s  # %s' % (rule, self.comment)
		rule = 'sub %s space by %s;' % (' '.join(self.inputPsNames), self.outputPsName)
		self.subRuleSpace = rule if self.comment is None else '%s  # %s' % (rule, self.comment)

def readAsukiSource(filename):
	asuki = {}
	index = 0
	with open(filename, 'r') as f:
		for line in f:
			line = line.strip()
			if len(line) > 0 and line[0] != '#':
				a = AsukiLine(index, line)
				if a.sortKey[0] not in asuki:
					asuki[a.sortKey[0]] = {}
				asuki[a.sortKey[0]][a.sortKey[1]] = a
				index += 1
	return asuki

def writeAsukiFeatures(filename, asuki, spaces=True):
	with open(filename, 'w') as f:
		f.write('feature liga {\n\n')
		for sk0 in sorted(asuki.keys()):
			if spaces:
				f.write('  # Sequences of length %d (%d + space)\n' % (1-sk0, -sk0))
				for sk1 in sorted(asuki[sk0].keys()):
					f.write('  %s\n' % asuki[sk0][sk1].subRuleSpace)
				f.write('\n')
			f.write('  # Sequences of length %d\n' % -sk0)
			for sk1 in sorted(asuki[sk0].keys()):
				f.write('  %s\n' % asuki[sk0][sk1].subRule)
			f.write('\n')
		f.write('} liga;\n')

def readSFDGlyphNames(filename):
	currentName = None
	glyphNames = []
	glyphWidths = {}
	with open(filename, 'r') as f:
		for line in f:
			line = line.strip()
			if line.startswith('StartChar: '):
				currentName = line.split(' ', 1)[1]
				glyphNames.append(currentName)
			if line.startswith('Width: '):
				width = int(line.split(' ', 1)[1])
				glyphWidths[currentName] = width
	return (glyphNames, glyphWidths)

def readKbitxGlyphNames(filename):
	currentName = None
	glyphNames = []
	glyphWidths = {}
	with open(filename, 'r') as f:
		for line in f:
			m = re.search('<g ([un])="([^\"]+)"', line)
			if m:
				if m.group(1) == 'u':
					currentName = psName(int(m.group(2)))
					glyphNames.append(currentName)
				if m.group(1) == 'n':
					currentName = m.group(2)
					glyphNames.append(currentName)
				m = re.search(' w="([0-9]+)"', line)
				if m:
					width = int(m.group(1))
					glyphWidths[currentName] = width
	return (glyphNames, glyphWidths)

def readGlyphNames(filename):
	if filename.endswith('.sfd'):
		return readSFDGlyphNames(filename)
	if filename.endswith('.kbitx'):
		return readKbitxGlyphNames(filename)
	raise ValueError(filename)

def kijeExtensionTriples(glyphNames):
	for gn in glyphNames:
		ext = '%s.kijext' % gn
		end = '%s.kijend' % gn
		if ext in glyphNames and end in glyphNames:
			yield gn, ext, end

class ExtendableLine:
	def __init__(self, index, line):
		self.index = index
		fields = line.split('#', 1)
		self.comment = fields[1].strip() if len(fields) > 1 else None
		fields = re.split(r'\s+', fields[0].strip())
		self.base = fields[0] if len(fields) > 0 and fields[0][0] != '-' else None
		self.forward = fields[1] if len(fields) > 1 and fields[1][0] != '-' else None
		self.reverse = fields[2] if len(fields) > 2 and fields[2][0] != '-' else None
		self.both = fields[3] if len(fields) > 3 and fields[3][0] != '-' else None
		self.kijeReverse = fields[4] if len(fields) > 4 and fields[4][0] != '-' else None
		self.kijeBoth = fields[5] if len(fields) > 5 and fields[5][0] != '-' else None

	def wrap(self, text, additional=None):
		if text is not None:
			if self.comment is not None:
				if additional is not None:
					return '%s  # %s, %s' % (text, self.comment, additional)
				return '%s  # %s' % (text, self.comment)
			if additional is not None:
				return '%s  # %s' % (text, additional)
		return text

class ApplyRuleLine:
	def __init__(self, allow, rule):
		self.allow = allow
		if rule == 'all' or rule == '*':
			self.type = 'a'
			return
		if rule.startswith('U+') or rule.startswith('u+'):
			try:
				self.ranges = [tuple(int(c, 16) for c in r.split('-', 1)) for r in rule[2:].split('+')]
				self.type = 'u'
				return
			except ValueError:
				pass
		if rule.startswith('/') and rule.endswith('/'):
			try:
				self.regex = re.compile(rule[1:-1])
				self.type = 'r'
				return
			except re.error:
				pass
		if rule.startswith('^') or rule.endswith('$'):
			try:
				self.regex = re.compile(rule)
				self.type = 'r'
				return
			except re.error:
				pass
		self.rule = rule
		self.type = 's'

	def appliesTo(self, name, splitName=None, codePoint=None):
		if splitName is None:
			splitName = name.split('.')
		if codePoint is None:
			codePoint = psUnicode(splitName[0])
		if self.type == 'a':
			return True
		if self.type == 'u':
			for r in self.ranges:
				if len(r) == 2 and r[0] <= codePoint <= r[1]:
					return True
				if len(r) == 1 and r[0] == codePoint:
					return True
			return False
		if self.type == 'r':
			if self.regex.match(name):
				return True
			return False
		return self.rule == name

def readExtendableSource(filename):
	applyRules = []
	extendable = []
	index = 0
	with open(filename, 'r') as f:
		for line in f:
			line = line.strip()
			if len(line) > 0 and line[0] != '#':
				fields = line.split('#', 1)
				fields = re.split(r'\s+', fields[0].strip(), 1)
				if fields[0] == 'allow' or fields[0] == 'deny':
					a = ApplyRuleLine(fields[0] == 'allow', fields[1])
					applyRules.append(a)
				else:
					e = ExtendableLine(index, line)
					extendable.append(e)
					index += 1
	return (extendable, applyRules)

def forwardExtendablePairs(extendable):
	for e in extendable:
		if e.base is not None and e.forward is not None:
			yield e.wrap(e.base), e.wrap(e.forward)
	for e in extendable:
		if e.reverse is not None and e.both is not None:
			yield e.wrap(e.reverse, 'reverse-extended'), e.wrap(e.both, 'reverse-extended')
	for e in extendable:
		if e.kijeReverse is not None and e.kijeBoth is not None:
			yield e.wrap(e.kijeReverse, 'reverse-extended'), e.wrap(e.kijeBoth, 'reverse-extended')

def reverseExtendablePairs(extendable):
	for e in extendable:
		if e.base is not None and e.reverse is not None:
			yield e.wrap(e.base), e.wrap(e.reverse)
	for e in extendable:
		if e.forward is not None and e.both is not None:
			yield e.wrap(e.forward, 'extended'), e.wrap(e.both, 'extended')

def kijeExtendablePairs(extendable):
	for e in extendable:
		if e.base is not None and e.kijeReverse is not None:
			yield e.wrap(e.base), e.wrap(e.kijeReverse)
	for e in extendable:
		if e.forward is not None and e.kijeBoth is not None:
			yield e.wrap(e.forward, 'extended'), e.wrap(e.kijeBoth, 'extended')

def extendedGlyphNames(extendable):
	for e in extendable:
		if e.forward is not None:
			yield e.forward
		if e.reverse is not None:
			yield e.reverse
		if e.both is not None:
			yield e.both
		if e.kijeReverse is not None:
			yield e.kijeReverse
		if e.kijeBoth is not None:
			yield e.kijeBoth

# Glyphs with names starting with these prefixes shall not be automatically cartouched.
PREFIX_EXCEPTIONS = [
	# sitelen pona format controls
	'uF1990', 'uF1991', 'uF1992', 'uF1993', 'uF1994', 'uF1995',
	'uF1996', 'uF1997', 'uF1998', 'uF1999', 'uF199A', 'uF199B',
	# titi pula format controls
	'uF1C7E', 'uF1C7F'
];

# Glyphs with names ending with these suffixes shall not be automatically cartouched.
SUFFIX_EXCEPTIONS = [
	'cartouche', 'extension', 'kijext', 'kijend',
	'ccart', 'cext', 'ecart', 'eext'
];

def writeExtendableFeatures(
	filename, glyphNames, glyphWidths, extendable, applyRules,
	prefixExceptions=PREFIX_EXCEPTIONS, suffixExceptions=SUFFIX_EXCEPTIONS
):
	cartGN = [gn for gn in glyphNames if gn.endswith('.cartouche')]
	extGN = [gn for gn in glyphNames if gn.endswith('.extension')]
	cartlessGN = [gn.rsplit('.', 1)[0] for gn in cartGN]
	extlessGN = [gn.rsplit('.', 1)[0] for gn in extGN]
	cartZW = [int(gn[1:-6]) for gn in glyphNames if re.match(r'^z[0-9]+[.]ccart$', gn) and '%s.ecart' % gn[0:-6] in glyphNames]
	extZW = [int(gn[1:-5]) for gn in glyphNames if re.match(r'^z[0-9]+[.]cext$', gn) and '%s.eext' % gn[0:-5] in glyphNames]
	fxPairs = list(forwardExtendablePairs(extendable))
	rxPairs = list(reverseExtendablePairs(extendable))
	kxTriples = list(kijeExtensionTriples(glyphNames))
	kxPairs = list(kijeExtendablePairs(extendable))
	exGN = list(extendedGlyphNames(extendable))
	def cartableFn(gn):
		gnc = gn.split('.')
		cp = psUnicode(gnc[0])
		allow = False
		for rule in applyRules:
			if rule.appliesTo(gn, gnc, cp):
				allow = rule.allow
		return allow and not (
			gn in exGN or
			gnc[0] in prefixExceptions or
			gnc[-1] in suffixExceptions
		)
	cartableGN = [gn for gn in glyphNames if cartableFn(gn)]
	with open(filename, 'w') as f:
		if cartGN:
			f.write('# all glyphs with explicit forms for inclusion in a cartouche\n')
			f.write('@spCartoucheless = [%s];\n\n' % ' '.join(cartlessGN))
			f.write('# corresponding glyphs with cartouche extension\n')
			f.write('@spCartouche = [%s];\n\n' % ' '.join(cartGN));
		if extGN:
			f.write('# all glyphs with explicit forms for inclusion in a long glyph\n')
			f.write('@spExtensionless = [%s];\n\n' % ' '.join(extlessGN))
			f.write('# corresponding glyphs with long glyph extension\n')
			f.write('@spExtension = [%s];\n\n' % ' '.join(extGN))
		if cartZW and cartableGN:
			f.write('# zero-width cartouche extension glyphs per advance width class\n')
			f.write('@spCartoucheComb = [%s];\n' % ' '.join('z%d.ccart' % zw for zw in cartZW))
			f.write('@spCartoucheEncl = [%s];\n\n' % ' '.join('z%d.ecart' % zw for zw in cartZW))
		if extZW and cartableGN:
			f.write('# zero-width long glyph extension glyphs per advance width class\n')
			f.write('@spExtensionComb = [%s];\n' % ' '.join('z%d.cext' % zw for zw in extZW))
			f.write('@spExtensionEncl = [%s];\n\n' % ' '.join('z%d.eext' % zw for zw in extZW))
		if cartZW and cartableGN:
			f.write('# glyphs that can be implicitly included in cartouches using the lookup tables below\n')
			f.write('@spCartoucheAuto = [%s];\n\n' % ' '.join(gn for gn in cartableGN if gn not in cartlessGN))
		if extZW and cartableGN:
			f.write('# glyphs that can be implicitly included in long glyphs using the lookup tables below\n')
			f.write('@spExtensionAuto = [%s];\n\n' % ' '.join(gn for gn in cartableGN if gn not in extlessGN))
		if cartGN or (cartZW and cartableGN):
			f.write('# lookup table used when extending cartouches to the right\n')
			f.write('lookup spCartoucheApplyForward {\n')
			if cartGN:
				f.write('  sub @spCartoucheless by @spCartouche;\n')
			if cartZW and cartableGN:
				for gn in cartableGN:
					if gn not in cartlessGN:
						zw = min(zw for zw in cartZW if zw >= glyphWidths[gn])
						if zw is not None:
							f.write('  sub %s by %s z%d.ccart;\n' % (gn, gn, zw))
			f.write('} spCartoucheApplyForward;\n\n')
			f.write('# lookup table used when extending cartouches to the left\n')
			f.write('lookup spCartoucheApplyBackward {\n')
			if cartGN:
				f.write('  sub @spCartoucheless by @spCartouche;\n')
			if cartZW and cartableGN:
				for gn in cartableGN:
					if gn not in cartlessGN:
						zw = min(zw for zw in cartZW if zw >= glyphWidths[gn])
						if zw is not None:
							f.write('  sub %s by z%d.ecart %s;\n' % (gn, zw, gn))
			f.write('} spCartoucheApplyBackward;\n\n')
		if extGN or (extZW and cartableGN):
			f.write('# lookup table used when extending long glyphs to the right\n')
			f.write('lookup spExtensionApplyForward {\n')
			if extGN:
				f.write('  sub @spExtensionless by @spExtension;\n')
			if extZW and cartableGN:
				for gn in cartableGN:
					if gn not in extlessGN:
						zw = min(zw for zw in extZW if zw >= glyphWidths[gn])
						if zw is not None:
							f.write('  sub %s by %s z%d.cext;\n' % (gn, gn, zw))
			f.write('} spExtensionApplyForward;\n\n')
			f.write('# lookup table used when extending long glyphs to the left\n')
			f.write('lookup spExtensionApplyBackward {\n')
			if extGN:
				f.write('  sub @spExtensionless by @spExtension;\n')
			if extZW and cartableGN:
				for gn in cartableGN:
					if gn not in extlessGN:
						zw = min(zw for zw in extZW if zw >= glyphWidths[gn])
						if zw is not None:
							f.write('  sub %s by z%d.eext %s;\n' % (gn, zw, gn))
			f.write('} spExtensionApplyBackward;\n\n')
		if fxPairs:
			f.write('# sitelen pona ideographs that can be made long on the right side\n')
			f.write('@spExtendable = [\n%s];\n\n' % ''.join('  %s\n' % a for a, e in fxPairs))
			f.write('# corresponding glyphs made long on the right side\n')
			f.write('@spExtended = [\n%s];\n\n' % ''.join('  %s\n' % e for a, e in fxPairs))
		if rxPairs:
			f.write('# sitelen pona ideographs that can be made long on the left side\n')
			f.write('@spReverseExtendable = [\n%s];\n\n' % ''.join('  %s\n' % a for a, e in rxPairs))
			f.write('# corresponding glyphs made long on the left side\n')
			f.write('@spReverseExtended = [\n%s];\n\n' % ''.join('  %s\n' % e for a, e in rxPairs))
		if kxTriples and kxPairs:
			f.write('# reverse long glyph extension for kijetesantakalu\n')
			f.write('@spKijeExtensionless = [%s];\n' % ' '.join(gn for gn, ext, end in kxTriples))
			f.write('@spKijeExtension = [%s];\n' % ' '.join(ext for gn, ext, end in kxTriples))
			f.write('@spKijeExtensionEnd = [%s];\n' % ' '.join(end for gn, ext, end in kxTriples))
			f.write('@spKijeExtendable = [\n%s];\n' % ''.join('  %s\n' % a for a, e in kxPairs))
			f.write('@spKijeExtended = [\n%s];\n' % ''.join('  %s\n' % e for a, e in kxPairs))

class JoinerLine:
	def __init__(self, index, line):
		self.index = index
		fields = line.split('#', 1)
		self.comment = fields[1].strip() if len(fields) > 1 else None
		fields = re.split(r'\s+', fields[0].strip(), 1)
		self.outputPsName = fields[0]
		self.inputSource = fields[1]
		self.inputSourceItems = [fields[1]]
		self.inputSourceDelim = None
		self.inputSourceJoiner = None
		for delim, joiner in [('-','uni200D'),('+','uni200D'),('^','uF1995'),('*','uF1996')]:
			if delim in fields[1]:
				self.inputSourceItems = fields[1].split(delim)
				self.inputSourceDelim = delim
				self.inputSourceJoiner = joiner

	def subRule(self, nimi, includeComment=True):
		joiner = ' %s ' % self.inputSourceJoiner
		names = [i[1:] if i[0] == '\\' else nimi[i] for i in self.inputSourceItems]
		rule = 'sub %s by %s;' % (joiner.join(names), self.outputPsName)
		return rule if self.comment is None or not includeComment else '%s  # %s' % (rule, self.comment)

	def sortKey(self, nimi):
		return (
			(
				-len(self.inputSourceItems),
				self.inputSourceJoiner != 'uni200D',
				None if self.comment is None else '+' in self.comment
			),
			self.subRule(nimi, False)
		)

def readJoinerSource(filename, joiners=None, nimi=None):
	if joiners is None:
		joiners = {}
	if nimi is None:
		nimi = {}
	index = 0
	with open(filename, 'r') as f:
		for line in f:
			line = line.strip()
			if len(line) > 0 and line[0] != '#':
				j = JoinerLine(index, line)
				if j.inputSourceDelim is None:
					nimi[j.inputSource] = j.outputPsName
				elif j.inputSourceDelim != '+':
					sk = j.sortKey(nimi)
					if sk[0] not in joiners:
						joiners[sk[0]] = {}
					if sk[1] not in joiners[sk[0]]:
						joiners[sk[0]][sk[1]] = j
				index += 1
	return joiners, nimi

def writeJoinerFeatures(filename, joiners, nimi):
	with open(filename, 'w') as f:
		f.write('feature liga {\n\n')
		for sk0 in sorted(joiners.keys()):
			if sk0[2]:
				pass
			elif sk0[1]:
				f.write('  # Sequences of length %d, using stacking or scaling joiners\n' % -sk0[0])
			else:
				f.write('  # Sequences of length %d, using zero width joiners\n' % -sk0[0])
			for sk1 in sorted(joiners[sk0].keys()):
				f.write('  %s\n' % joiners[sk0][sk1].subRule(nimi))
			f.write('\n')
		f.write('} liga;\n')

def main(args):
	# Default arguments
	asukiSrc = 'asuki.txt'
	asukiOut = 'asuki.fea'
	atukiSrc = 'atuki.txt'
	atukiOut = 'atuki.fea'
	extendableSrc = 'extendable.txt'
	extendableOut = 'extendable.fea'
	joinerSrc = 'joiners.txt'
	joinerOut = 'joiners.fea'
	glyphNameSrc = None
	spaces = True
	# Parse arguments
	argType = None
	for arg in args:
		if argType is not None:
			if argType == '-a':
				asukiSrc = arg
			if argType == '-A':
				asukiOut = arg
			if argType == '-t':
				atukiSrc = arg
			if argType == '-T':
				atukiOut = arg
			if argType == '-e':
				extendableSrc = arg
			if argType == '-E':
				extendableOut = arg
			if argType == '-j':
				joinerSrc = arg
			if argType == '-J':
				joinerOut = arg
			if argType == '-g':
				glyphNameSrc = arg
			argType = None
		elif arg.startswith('-'):
			if arg in ['-a', '-A', '-t', '-T', '-e', '-E', '-j', '-J', '-g']:
				argType = arg
			elif arg == '-s':
				spaces = False
			elif arg == '-S':
				spaces = True
			else:
				print(('Unknown option: %s' % arg), file=sys.stderr)
		else:
			glyphNameSrc = arg
	# Build
	if glyphNameSrc is None:
		print('No source font provided', file=sys.stderr)
	else:
		asuki = readAsukiSource(asukiSrc)
		writeAsukiFeatures(asukiOut, asuki, spaces=spaces)
		atuki = readAsukiSource(atukiSrc)
		writeAsukiFeatures(atukiOut, atuki, spaces=spaces)
		glyphNames, glyphWidths = readGlyphNames(glyphNameSrc)
		extendable, applyRules = readExtendableSource(extendableSrc)
		writeExtendableFeatures(extendableOut, glyphNames, glyphWidths, extendable, applyRules)
		joiners, nimi = readJoinerSource(asukiSrc)
		joiners, nimi = readJoinerSource(joinerSrc, joiners, nimi)
		writeJoinerFeatures(joinerOut, joiners, nimi)

if __name__ == '__main__':
	main(sys.argv[1:])
