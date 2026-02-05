#!/usr/bin/env python

from __future__ import print_function
from kbnpname import kbnpName
from psname import psNames, psUnicode
import re
import sys

# --- Reading glyph names and widths from font source files --------------------

def readSFDGlyphWidths(path):
	widths = {}
	with open(path, 'r') as f:
		name = None
		for line in f:
			if line.startswith('StartChar: '):
				name = line.strip().split(' ', 1)[1]
			if line.startswith('Width: '):
				widths[name] = int(line.strip().split(' ', 1)[1])
	return widths

def readKbitxGlyphWidths(path):
	widths = {}
	with open(path, 'r') as f:
		name = None
		for line in f:
			m = re.search('<g ([un])="([^\"]+)"', line)
			if m:
				if m.group(1) == 'u':
					name = kbnpName(int(m.group(2)))
				if m.group(1) == 'n':
					name = m.group(2)
				m = re.search(' w="([0-9]+)"', line)
				if m:
					widths[name] = int(m.group(1)) * 100
	return widths

def readGlyphWidths(path):
	if path.endswith('.sfd'):
		return readSFDGlyphWidths(path)
	if path.endswith('.kbitx'):
		return readKbitxGlyphWidths(path)
	raise ValueError(path)

# --- Rules for matching a set of glyphs by name or code point -----------------

class GlyphRule:
	def __init__(self, allow, rule):
		self.allow = allow
		if rule == 'all' or rule == '*':
			self.type = 'a'
		elif rule.startswith('U+') or rule.startswith('u+'):
			self.ranges = [tuple(int(c, 16) for c in r.split('-', 1)) for r in rule[2:].split('+')]
			self.type = 'u'
		elif rule.startswith('/') and rule.endswith('/'):
			self.regex = re.compile(rule[1:-1])
			self.type = 'r'
		elif rule.startswith('^') or rule.endswith('$'):
			self.regex = re.compile(rule)
			self.type = 'r'
		else:
			self.rule = rule
			self.type = 's'

	def match(self, name, splitName=None, codePoint=None):
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

class GlyphRuleSet:
	def __init__(self, allow):
		self.allow = allow
		self.rules = []

	def addRule(self, allow, rule):
		self.rules.append(GlyphRule(allow, rule))

	def match(self, name, splitName=None, codePoint=None):
		if splitName is None:
			splitName = name.split('.')
		if codePoint is None:
			codePoint = psUnicode(splitName[0])
		allow = self.allow
		for rule in self.rules:
			if rule.match(name, splitName, codePoint):
				allow = rule.allow
		return allow

# --- Building a database of information about sitelen pona glyphs -------------

# Keys for extended glyphs
FORWARD = 'FORWARD'
REVERSE = 'REVERSE'
BIDIRECTIONAL = 'BIDIRECTIONAL'
KIJETESANTAKALU_REVERSE = 'KIJETESANTAKALU_REVERSE'
KIJETESANTAKALU_BIDIRECTIONAL = 'KIJETESANTAKALU_BIDIRECTIONAL'

# Joiners for compound glyphs
ZERO_WIDTH_JOINER = '&'
SP_SCALING_JOINER = '+'
SP_STACKING_JOINER = '-'
JOINERS = {'&': 'uni200D', '+': 'uF1996', '-': 'uF1995'}
JOINER_RE = '([&+-])'

# Other stuff
TASUN_GLYPHS = ['tasun1', 'tasun2', 'tasun3', 'taa', 'a', 'aasun']

class GlyphInfo:
	def __init__(self, name, width):
		self.name = name
		self.names = [name]
		self.width = width
		self.comments = []
		self.asciiSequences = []

	def outputClass(self):
		return ('[%s]' % ' '.join(self.names)) if len(self.names) > 1 else self.name

	def outputComment(self):
		return ('  # %s' % '; '.join(self.comments)) if self.comments else ''

class GlyphCollection:
	def __init__(self, path):
		self.widths = readGlyphWidths(path)
		self.autocartouche = GlyphRuleSet(False)
		self.featureNames = {}
		self.featureVariants = {}
		self.glyphsByName = {}
		self.asciiSequences = {}
		self.joinerSequences = {}
		self.extendedVariants = {
			FORWARD: {},
			REVERSE: {},
			BIDIRECTIONAL: {},
			KIJETESANTAKALU_REVERSE: {},
			KIJETESANTAKALU_BIDIRECTIONAL: {}
		}

	def addAutocartoucheRule(self, allow, rule):
		self.autocartouche.addRule(allow, rule)

	def mapFeatureName(self, feature, name):
		self.featureNames[feature] = name
		self.featureVariants[feature] = {}

	def mapFeatureVariant(self, name, baseName, feature):
		self.featureVariants[feature][baseName] = name

	def addDictionaryEntry(self, dictionary, name, key, comment):
		if name in self.glyphsByName:
			g = self.glyphsByName[name]
		elif key in dictionary:
			g = dictionary[key]
		else:
			g = GlyphInfo(name, self.widths[name])
		if name not in g.names:
			g.names.append(name)
		if comment is not None and comment not in g.comments:
			g.comments.append(comment)
		self.glyphsByName[name] = g
		dictionary[key] = g
		return g

	def mapAsciiSequence(self, name, sequence, comment):
		g = self.addDictionaryEntry(self.asciiSequences, name, sequence, comment)
		if sequence not in g.asciiSequences:
			g.asciiSequences.append(sequence)

	def mapJoinerSequence(self, name, sequence, comment):
		self.addDictionaryEntry(self.joinerSequences, name, sequence, comment)

	def mapJoinerSequenceFallback(self, sequence, glyph, *fallbacks):
		if glyph is None:
			for fallback in fallbacks:
				if fallback is not None:
					self.joinerSequences[sequence] = fallback
					return

	def mapJoinerSequenceFallbacks(self):
		for joinerSequence in list(self.joinerSequences.keys()):
			zwjSequence = tuple((ZERO_WIDTH_JOINER if x in JOINERS else x) for x in joinerSequence)
			scaledSequence = tuple((SP_SCALING_JOINER if x in JOINERS else x) for x in joinerSequence)
			stackedSequence = tuple((SP_STACKING_JOINER if x in JOINERS else x) for x in joinerSequence)
			zwjGlyph = self.joinerSequences[zwjSequence] if zwjSequence in self.joinerSequences else None
			scaledGlyph = self.joinerSequences[scaledSequence] if scaledSequence in self.joinerSequences else None
			stackedGlyph = self.joinerSequences[stackedSequence] if stackedSequence in self.joinerSequences else None
			self.mapJoinerSequenceFallback(zwjSequence, zwjGlyph, scaledGlyph, stackedGlyph)
			self.mapJoinerSequenceFallback(scaledSequence, scaledGlyph, stackedGlyph)
			self.mapJoinerSequenceFallback(stackedSequence, stackedGlyph, scaledGlyph)

	def mapExtendedVariant(self, variant, name, baseName, comment):
		self.addDictionaryEntry(self.extendedVariants[variant], name, baseName, comment)

	def parseInfoLine(self, line):
		fields = line.split('#', 1)
		comment = fields[1].strip() if len(fields) > 1 else None
		fields = re.split(r'\s+', fields[0].strip())
		if fields[0] == '@allow' or fields[0] == '@deny':
			for rule in fields[1:]:
				self.addAutocartoucheRule(fields[0] == '@allow', rule)
			return
		m = re.match('^@(ss[0-9][0-9]|cv[0-9][0-9]([.][0-9]+)?)$', fields[0])
		if m:
			self.mapFeatureName(m.group(1), ' '.join(fields[1:]))
			return
		for name in fields[1:]:
			m = re.match('^(.+)[.](ss[0-9][0-9]|cv[0-9][0-9][.][0-9]+)$', name)
			if m:
				self.mapFeatureVariant(fields[0], m.group(1), m.group(2))
			elif len(name) > 2 and name.startswith('=') and name.endswith('_'):
				self.mapExtendedVariant(KIJETESANTAKALU_BIDIRECTIONAL, fields[0], name[1:-1], comment)
			elif len(name) > 1 and name.startswith('='):
				self.mapExtendedVariant(KIJETESANTAKALU_REVERSE, fields[0], name[1:], comment)
			elif len(name) > 2 and name.startswith('_') and name.endswith('_'):
				self.mapExtendedVariant(BIDIRECTIONAL, fields[0], name[1:-1], comment)
			elif len(name) > 1 and name.startswith('_'):
				self.mapExtendedVariant(REVERSE, fields[0], name[1:], comment)
			elif len(name) > 1 and name.endswith('_'):
				self.mapExtendedVariant(FORWARD, fields[0], name[:-1], comment)
			elif len(name) > 2 and name.startswith('"') and name.endswith('"'):
				self.mapAsciiSequence(fields[0], name[1:-1], comment)
			else:
				joinerSequence = tuple(re.split(JOINER_RE, name))
				if len(joinerSequence) > 1 and all(joinerSequence):
					self.mapJoinerSequence(fields[0], joinerSequence, comment)
				else:
					self.mapAsciiSequence(fields[0], name, comment)

	def parseInfoFile(self, path):
		with open(path, 'r') as f:
			for line in f:
				self.parseInfoLine(line)

	def parseInfoFinish(self):
		self.mapJoinerSequenceFallbacks()
		self.addAutocartoucheRule(False, 'U+F1990-F199B')  # sitelen pona format control characters
		self.addAutocartoucheRule(False, 'U+F199E-F199F')  # sitelen pona combining tally marks
		self.addAutocartoucheRule(False, 'U+F1C7E-F1C7F')  # titi pula format control characters
		self.addAutocartoucheRule(False, '^.+[.](cartouche|extension|kijext|kijend|ccart|cext|ecart|eext)$')

	def writeAsciiSequences(self, path, spaces=None, joiners=None, webkitFix=None):
		# Check parameters
		zeroWidthSpace = (self.widths['space'] == 0)
		allJoinersAscii = all(x in self.asciiSequences and self.asciiSequences[x].name == JOINERS[x] for x in JOINERS.keys())
		if spaces is None:
			spaces = not zeroWidthSpace
		if not spaces and not zeroWidthSpace:
			print('WARNING: Subs with spaces not being added to font with non-zero-width space', file=sys.stderr)
		if joiners is None:
			joiners = not allJoinersAscii
		if not joiners and not allJoinersAscii:
			print('WARNING: Subs with joiners not being added to font without ASCII joiners', file=sys.stderr)
		if webkitFix is None:
			webkitFix = zeroWidthSpace
		if webkitFix and not zeroWidthSpace:
			print('WARNING: WebKit fix being applied to font with non-zero-width space', file=sys.stderr)
		if not webkitFix and zeroWidthSpace:
			print('WARNING: WebKit fix not being applied to font with zero-width space', file=sys.stderr)
		# Gather all sequences grouped by length
		sequences = {}
		if joiners:
			for k in self.joinerSequences.keys():
				s = tuple(psNames(''.join(k)))
				if 'at' not in s and 'backslash' not in s:
					if len(s) not in sequences:
						sequences[len(s)] = {}
					sequences[len(s)][s] = self.joinerSequences[k]
		for k in self.asciiSequences.keys():
			s = tuple(psNames(k))
			if len(s) not in sequences:
				sequences[len(s)] = {}
			sequences[len(s)][s] = self.asciiSequences[k]
		# Write features to file
		with open(path, 'w') as f:
			f.write('feature liga {\n\n')
			for l in sorted(sequences.keys(), reverse=True):
				if spaces:
					f.write('  # Sequences of length %d (%d + space)\n' % (l + 1, l))
					for s in sorted(sequences[l].keys()):
						f.write('  sub %s space by %s;\n' % (' '.join(s), sequences[l][s].name))
					f.write('\n')
				f.write('  # Sequences of length %d\n' % l)
				for s in sorted(sequences[l].keys()):
					f.write('  sub %s by %s;\n' % (' '.join(s), sequences[l][s].name))
				f.write('\n')
			if webkitFix:
				f.write('  # WebKit fixes\n')
				f.write('  sub [uni00A0 space] space\' by uni00A0;\n')
				if 'uF1997' in self.widths:
					f.write('  sub space uF1997 by uF1997;\n')
				if 'uF199B' in self.widths:
					f.write('  sub uF199B space by uF199B;\n')
				f.write('\n')
			f.write('} liga;\n\n')

	def getJoinerGlyphClass(self, name):
		if name in JOINERS:
			return JOINERS[name]
		if name.startswith('@'):
			return '@sp_' + name[1:]
		if name.startswith('\\'):
			if name[1:] in self.glyphsByName:
				return self.glyphsByName[name[1:]].outputClass()
			return GlyphInfo(name[1:], self.widths[name[1:]]).outputClass()
		return self.asciiSequences[name].outputClass()

	def writeJoinerSequences(self, f):
		# Gather all sequences grouped by length
		sequences = {}
		for k in self.joinerSequences.keys():
			s = tuple(self.getJoinerGlyphClass(p) for p in k)
			if len(s) not in sequences:
				sequences[len(s)] = {}
			sequences[len(s)][s] = self.joinerSequences[k]
		# Find maximum number of tally marks
		maxTally = 0
		maxTallySequence = ','
		while maxTallySequence in self.asciiSequences:
			maxTally += 1
			maxTallySequence += ','
		# Write features to file
		f.write('feature rlig {\n\n')
		for l in sorted(sequences.keys(), reverse=True):
			f.write('  # Sequences of length %d\n' % l)
			for s in sorted(sequences[l].keys()):
				f.write('  sub %s by %s;%s\n' % (' '.join(s), sequences[l][s].name, sequences[l][s].outputComment()))
			f.write('\n')
		if maxTally > 1:
			gc = self.asciiSequences[','].outputClass()
			f.write('  # Tally marks\n')
			for n in range(maxTally, 1, -1):
				g = self.asciiSequences[maxTallySequence[0:n]]
				f.write('  sub %s by %s;%s\n' % (' '.join([gc] * n), g.name, g.outputComment()))
			f.write('\n')
		f.write('} rlig;\n\n')

	def generatePairs(self, g1, g2):
		g1comment = g1.outputComment()
		g2comment = g2.outputComment()
		for name in g1.names:
			yield (name + g1comment, g2.name + g2comment)

	def getForwardExtendablePairs(self):
		for k in self.extendedVariants[FORWARD].keys():
			for pair in self.generatePairs(self.asciiSequences[k], self.extendedVariants[FORWARD][k]):
				yield pair
		for k in self.extendedVariants[BIDIRECTIONAL].keys():
			if k in self.extendedVariants[REVERSE]:
				for pair in self.generatePairs(self.extendedVariants[REVERSE][k], self.extendedVariants[BIDIRECTIONAL][k]):
					yield pair
		for k in self.extendedVariants[KIJETESANTAKALU_BIDIRECTIONAL].keys():
			if k in self.extendedVariants[KIJETESANTAKALU_REVERSE]:
				for pair in self.generatePairs(self.extendedVariants[KIJETESANTAKALU_REVERSE][k], self.extendedVariants[KIJETESANTAKALU_BIDIRECTIONAL][k]):
					yield pair

	def getReverseExtendablePairs(self):
		for k in self.extendedVariants[REVERSE].keys():
			for pair in self.generatePairs(self.asciiSequences[k], self.extendedVariants[REVERSE][k]):
				yield pair
		for k in self.extendedVariants[BIDIRECTIONAL].keys():
			if k in self.extendedVariants[FORWARD]:
				for pair in self.generatePairs(self.extendedVariants[FORWARD][k], self.extendedVariants[BIDIRECTIONAL][k]):
					yield pair

	def getKijetesantakaluExtendablePairs(self):
		for k in self.extendedVariants[KIJETESANTAKALU_REVERSE].keys():
			for pair in self.generatePairs(self.asciiSequences[k], self.extendedVariants[KIJETESANTAKALU_REVERSE][k]):
				yield pair
		for k in self.extendedVariants[KIJETESANTAKALU_BIDIRECTIONAL].keys():
			if k in self.extendedVariants[FORWARD]:
				for pair in self.generatePairs(self.extendedVariants[FORWARD][k], self.extendedVariants[KIJETESANTAKALU_BIDIRECTIONAL][k]):
					yield pair

	def getKijetesantakaluExtensionTriples(self):
		for gn in self.widths.keys():
			ext = '%s.kijext' % gn
			end = '%s.kijend' % gn
			if ext in self.widths and end in self.widths:
				yield (gn, ext, end)

	def getExtendedGlyphNames(self):
		for variants in self.extendedVariants.values():
			for glyph in variants.values():
				for name in glyph.names:
					yield name

	def writeExtensionFeatures(self, f, rsubDepth=16):
		# Gather glyph names
		cartGN = [gn for gn in self.widths.keys() if gn.endswith('.cartouche')]
		extGN = [gn for gn in self.widths.keys() if gn.endswith('.extension')]
		cartlessGN = [gn.rsplit('.', 1)[0] for gn in cartGN]
		extlessGN = [gn.rsplit('.', 1)[0] for gn in extGN]
		cartZW = sorted(int(gn[1:-6]) for gn in self.widths.keys() if re.match(r'^z[0-9]+[.]ccart$', gn) and '%s.ecart' % gn[0:-6] in self.widths)
		extZW = sorted(int(gn[1:-5]) for gn in self.widths.keys() if re.match(r'^z[0-9]+[.]cext$', gn) and '%s.eext' % gn[0:-5] in self.widths)
		fxPairs = sorted(set(self.getForwardExtendablePairs()))
		rxPairs = sorted(set(self.getReverseExtendablePairs()))
		kxPairs = sorted(set(self.getKijetesantakaluExtendablePairs()))
		kxTriples = sorted(self.getKijetesantakaluExtensionTriples())
		extendedGN = set(self.getExtendedGlyphNames())
		cartableGN = [gn for gn in self.widths.keys() if self.autocartouche.match(gn) and gn not in extendedGN]
		# Write glyph classes
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
		if cartZW and cartableGN:
			f.write('# lookup table used when extending cartouches to the right\n')
			f.write('lookup spCartoucheApplyForward {\n')
			if cartGN:
				f.write('  sub @spCartoucheless by @spCartouche;\n')
			for gn in cartableGN:
				if gn not in cartlessGN:
					zw = min(zw for zw in cartZW if zw >= self.widths[gn])
					if zw is not None:
						f.write('  sub %s by %s z%d.ccart;\n' % (gn, gn, zw))
			f.write('} spCartoucheApplyForward;\n\n')
			f.write('# lookup table used when extending cartouches to the left\n')
			f.write('lookup spCartoucheApplyBackward {\n')
			if cartGN:
				f.write('  sub @spCartoucheless by @spCartouche;\n')
			for gn in cartableGN:
				if gn not in cartlessGN:
					zw = min(zw for zw in cartZW if zw >= self.widths[gn])
					if zw is not None:
						f.write('  sub %s by z%d.ecart %s;\n' % (gn, zw, gn))
			f.write('} spCartoucheApplyBackward;\n\n')
		if extZW and cartableGN:
			f.write('# lookup table used when extending long glyphs to the right\n')
			f.write('lookup spExtensionApplyForward {\n')
			if extGN:
				f.write('  sub @spExtensionless by @spExtension;\n')
			for gn in cartableGN:
				if gn not in extlessGN:
					zw = min(zw for zw in extZW if zw >= self.widths[gn])
					if zw is not None:
						f.write('  sub %s by %s z%d.cext;\n' % (gn, gn, zw))
			f.write('} spExtensionApplyForward;\n\n')
			f.write('# lookup table used when extending long glyphs to the left\n')
			f.write('lookup spExtensionApplyBackward {\n')
			if extGN:
				f.write('  sub @spExtensionless by @spExtension;\n')
			for gn in cartableGN:
				if gn not in extlessGN:
					zw = min(zw for zw in extZW if zw >= self.widths[gn])
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
			f.write('@spKijeExtended = [\n%s];\n\n' % ''.join('  %s\n' % e for a, e in kxPairs))
		if cartGN or (cartZW and cartableGN):
			spCartoucheStart = [gn for gn in ['uF1990', 'uF1992', 'uF1C7E'] if gn in self.widths]
			spCartoucheEnd = [gn for gn in ['uF1991', 'uF1C7F'] if gn in self.widths]
			if cartGN:
				spCartoucheStart.append('@spCartouche')
				spCartoucheEnd.append('@spCartouche')
			if cartZW and cartableGN:
				spCartoucheStart.append('@spCartoucheComb')
				spCartoucheEnd.append('@spCartoucheEncl')
			f.write('@spCartoucheStart = [%s];\n' % ' '.join(spCartoucheStart))
			f.write('@spCartoucheEnd = [%s];\n\n' % ' '.join(spCartoucheEnd))
		if extGN or (extZW and cartableGN):
			spExtensionStart = [gn for gn in ['uF1997', 'uF1999', 'uF199A'] if gn in self.widths]
			spExtensionEnd = [gn for gn in ['uF1998', 'uF199B'] if gn in self.widths]
			if extGN:
				spExtensionStart.append('@spExtension')
				spExtensionEnd.append('@spExtension')
			if extZW and cartableGN:
				spExtensionStart.append('@spExtensionComb')
				spExtensionEnd.append('@spExtensionEncl')
			f.write('@spExtensionStart = [%s];\n' % ' '.join(spExtensionStart))
			f.write('@spExtensionEnd = [%s];\n\n' % ' '.join(spExtensionEnd))
		# Write substitution rules
		f.write('feature calt {\n\n')
		if all(x in self.asciiSequences for x in TASUN_GLYPHS):
			tasunGlyphs = [self.asciiSequences[x] for x in TASUN_GLYPHS]
			f.write('  # LONG TASUN\n\n')
			f.write('  # extend tasun to the right\n')
			f.write('  lookup spTasunForward {\n')
			f.write('    sub [%s %s %s] %s\' by %s;\n' % tuple(tasunGlyphs[i].name for i in [0, 1, 3, 4, 1]))
			f.write('  } spTasunForward;\n\n')
			f.write('  # extend tasun to the left\n')
			f.write('  lookup spTasunBackward {\n')
			f.write('    rsub %s\' [%s %s %s] by %s;\n' % tuple(tasunGlyphs[i].name for i in [4, 1, 2, 5, 1]))
			f.write('  } spTasunBackward;\n\n')
		if cartGN or (cartZW and cartableGN):
			f.write('  # CARTOUCHES\n\n')
			f.write('  # extend cartouches across ideographs to the right\n')
			f.write('  lookup spCartoucheForward {\n')
			if cartZW and cartableGN:
				if cartGN:
					f.write('    sub @spCartoucheStart [@spCartoucheless @spCartoucheAuto]\' lookup spCartoucheApplyForward;\n')
				else:
					f.write('    sub @spCartoucheStart @spCartoucheAuto\' lookup spCartoucheApplyForward;\n')
			else:
				f.write('    sub @spCartoucheStart @spCartoucheless\' by @spCartouche;\n')
			f.write('  } spCartoucheForward;\n\n')
			f.write('  # extend cartouches across ideographs to the left\n')
			if cartZW and cartableGN:
				for i in range(1, rsubDepth + 1):
					if cartGN:
						f.write('  lookup spCartoucheBackwardRsub%02d { rsub @spCartoucheless\' @spCartoucheEnd by @spCartouche; } spCartoucheBackwardRsub%02d;\n' % (i, i))
					f.write('  lookup spCartoucheBackwardFsub%02d { sub @spCartoucheAuto\' lookup spCartoucheApplyBackward @spCartoucheEnd; } spCartoucheBackwardFsub%02d;\n' % (i, i))
				f.write('  lookup spCartoucheBackwardCleanup { sub @spCartoucheEncl\' @spCartoucheEncl by NULL; } spCartoucheBackwardCleanup;\n\n')
			else:
				f.write('  lookup spCartoucheBackward {\n')
				f.write('    rsub @spCartoucheless\' @spCartoucheEnd by @spCartouche;\n')
				f.write('  } spCartoucheBackward;\n\n')
		if kxTriples and kxPairs:
			f.write('  # REVERSE EXTENDED KIJETESANTAKALU\n\n')
			f.write('  lookup spExtensionKijeStart {\n')
			f.write('    sub @spKijeExtensionless\' uF199B [@spKijeExtendable @spKijeExtended] by @spKijeExtension;\n')
			f.write('    sub [@spKijeExtensionless @spKijeExtension] uF199B @spKijeExtendable\' by @spKijeExtended;\n')
			f.write('  } spExtensionKijeStart;\n\n')
			f.write('  lookup spExtensionKijeContinue {\n')
			f.write('    rsub @spKijeExtensionless\' @spKijeExtension by @spKijeExtension;\n')
			f.write('  } spExtensionKijeContinue;\n\n')
			f.write('  lookup spExtensionKijeEnd {\n')
			f.write('    sub uF199A @spKijeExtension\' by @spKijeExtensionEnd;\n')
			f.write('  } spExtensionKijeEnd;\n\n')
		if fxPairs or rxPairs or extGN or (extZW and cartableGN):
			f.write('  # LONG GLYPHS\n\n')
			if fxPairs:
				f.write('  # replace ideograph + start of long glyph with glyph extended to the right\n')
				f.write('  lookup spExtensionNormal {\n')
				f.write('    sub @spExtendable\' uF1997 by @spExtended;\n')
				f.write('  } spExtensionNormal;\n\n')
			if rxPairs:
				f.write('  # replace end of reverse long glyph + ideograph with glyph extended to the left\n')
				f.write('  lookup spExtensionReverse {\n')
				f.write('    sub uF199B @spReverseExtendable\' by @spReverseExtended;\n')
				f.write('  } spExtensionReverse;\n\n')
			if extGN or (extZW and cartableGN):
				f.write('  # extend long glyphs across ideographs to the right\n')
				f.write('  lookup spExtensionForward {\n')
				if extZW and cartableGN:
					if extGN:
						f.write('    sub @spExtensionStart [@spExtensionless @spExtensionAuto]\' lookup spExtensionApplyForward;\n')
					else:
						f.write('    sub @spExtensionStart @spExtensionAuto\' lookup spExtensionApplyForward;\n')
				else:
					f.write('    sub @spExtensionStart @spExtensionless\' by @spExtension;\n')
				f.write('  } spExtensionForward;\n\n')
				f.write('  # extend long glyphs across ideographs to the left\n')
				if extZW and cartableGN:
					for i in range(1, rsubDepth + 1):
						if extGN:
							f.write('  lookup spExtensionBackwardRsub%02d { rsub @spExtensionless\' @spExtensionEnd by @spExtension; } spExtensionBackwardRsub%02d;\n' % (i, i))
						f.write('  lookup spExtensionBackwardFsub%02d { sub @spExtensionAuto\' lookup spExtensionApplyBackward @spExtensionEnd; } spExtensionBackwardFsub%02d;\n' % (i, i))
					f.write('  lookup spExtensionBackwardCleanup { sub @spExtensionEncl\' @spExtensionEncl by NULL; } spExtensionBackwardCleanup;\n\n')
				else:
					f.write('  lookup spExtensionBackward {\n')
					f.write('    rsub @spExtensionless\' @spExtensionEnd by @spExtension;\n')
					f.write('  } spExtensionBackward;\n\n')
		f.write('} calt;\n\n')

	def getVariantGlyphNames(self, name):
		if name.startswith('\\'):
			if name[1:] in self.glyphsByName:
				return self.glyphsByName[name[1:]].names
			return GlyphInfo(name[1:], self.widths[name[1:]]).names
		return self.asciiSequences[name].names

	def writeVariantFeatures(self, f):
		# Collect all glyph variants for use in joiner sequences
		collections = {}
		def collect(bn, vn):
			if bn in self.glyphsByName and self.glyphsByName[bn].asciiSequences:
				cn = self.glyphsByName[bn].asciiSequences[0]
				if cn not in collections:
					collections[cn] = [bn]
				if vn not in collections[cn]:
					collections[cn].append(vn)
		# Gather randomized glyph variants
		randomized = {}
		for gn in self.widths.keys():
			if '.rand' in gn:
				o = gn.index('.rand')
				bn = gn[:o]
				if bn in self.glyphsByName:
					if bn not in randomized:
						randomized[bn] = [bn]
					vn = gn[:o+1] + gn[o+1:].split('.', 1)[0]
					if vn not in randomized[bn]:
						randomized[bn].append(vn)
					collect(bn, vn)
		# Gather stylistic sets
		stylisticSets = {}
		for feature in [('ss%02d' % i) for i in range(0, 100)]:
			if feature in self.featureVariants and self.featureVariants[feature]:
				stylisticSets[feature] = {}
				for k in self.featureVariants[feature].keys():
					for name in self.getVariantGlyphNames(k):
						stylisticSets[feature][name] = self.featureVariants[feature][k]
						collect(name, self.featureVariants[feature][k])
		# Gather character variants
		characterVariants = {}
		for feature in [('cv%02d' % i) for i in range(0, 100)]:
			subfeatures = [k for k in self.featureVariants.keys() if k.startswith(feature) and self.featureVariants[k]]
			if subfeatures:
				characterVariants[feature] = {}
				for subfeature in subfeatures:
					characterVariants[feature][subfeature] = {}
					for k in self.featureVariants[subfeature].keys():
						for name in (self.glyphsByName[k[1:]] if k.startswith('\\') else self.asciiSequences[k]).names:
							characterVariants[feature][subfeature][name] = self.featureVariants[subfeature][k]
							collect(name, self.featureVariants[subfeature][k])
		# Write collections
		if collections:
			for cn in sorted(collections.keys()):
				f.write('@sp_%s = [%s];\n' % (cn, ' '.join(sorted(collections[cn]))))
			f.write('\n')
		# Write randomization feature
		if randomized:
			f.write('feature rand {\n')
			for bn in sorted(randomized.keys()):
				f.write('  sub %s from [%s];%s\n' % (bn, ' '.join(sorted(randomized[bn])), self.glyphsByName[bn].outputComment()))
			f.write('} rand;\n\n')
		# Write stylistic set features
		for feature in sorted(stylisticSets.keys()):
			f.write('feature %s {\n' % feature)
			if feature in self.featureNames and self.featureNames[feature]:
				f.write('  featureNames {\n')
				f.write('    name 3 1 1033 "%s";\n' % self.featureNames[feature])
				f.write('    name 1 0 0 "%s";\n' % self.featureNames[feature])
				f.write('  };\n')
			for bn in sorted(stylisticSets[feature].keys()):
				vn = stylisticSets[feature][bn]
				f.write('  sub %s by %s;%s\n' % (bn, vn, self.glyphsByName[vn].outputComment()))
			f.write('} %s;\n\n' % feature)
		# Write character variant features
		for feature in sorted(characterVariants.keys()):
			subfeatures = sorted(characterVariants[feature].keys())
			subfeatureNames = [(self.featureNames[x] if x in self.featureNames else '') for x in subfeatures]
			characters = sorted(set(sum([list(characterVariants[feature][x].keys()) for x in subfeatures], [])))
			f.write('feature %s {\n' % feature)
			f.write('  cvParameters {\n')
			if feature in self.featureNames and self.featureNames[feature]:
				f.write('    FeatUILabelNameID {\n')
				f.write('      name 3 1 1033 "%s";\n' % self.featureNames[feature])
				f.write('      name 1 0 0 "%s";\n' % self.featureNames[feature])
				f.write('    };\n')
			if any(subfeatureNames):
				for subfeatureName in subfeatureNames:
					f.write('    ParamUILabelNameID {\n')
					f.write('      name 3 1 1033 "%s";\n' % subfeatureName)
					f.write('      name 1 0 0 "%s";\n' % subfeatureName)
					f.write('    };\n')
			for cp in [psUnicode(c) for c in characters]:
				if cp >= 0:
					f.write('    Character 0x%04X;\n' % cp)
			f.write('  };\n')
			for c in characters:
				replacements = [(characterVariants[feature][x][c] if c in characterVariants[feature][x] else c) for x in subfeatures]
				if len(replacements) > 1:
					f.write('  sub %s from [%s];%s\n' % (c, ' '.join(replacements), self.glyphsByName[c].outputComment()))
				else:
					f.write('  sub %s by %s;%s\n' % (c, replacements[0], self.glyphsByName[c].outputComment()))
			f.write('} %s;\n\n' % feature)

	def writeFeatureFile(self, path, rsubDepth=16):
		with open(path, 'w') as f:
			self.writeVariantFeatures(f)
			self.writeJoinerSequences(f)
			self.writeExtensionFeatures(f, rsubDepth)

# --- Parsing arguments to this script -----------------------------------------

def main(args):
	# Default file names
	fontFile = None
	inputFile = 'sitelenpona.txt'
	asciiFile = 'spascii.fea'
	outputFile = 'sitelenpona.fea'
	# Options for ASCII sequences
	spaces = None
	joiners = None
	webkitFix = None
	rsubDepth = 16
	# Parse arguments
	argType = None
	for arg in args:
		if argType is not None:
			if argType == '-f':
				fontFile = arg
			if argType == '-i':
				inputFile = arg
			if argType == '-a':
				asciiFile = arg
			if argType == '-o':
				outputFile = arg
			if argType == '-r':
				rsubDepth = int(arg)
			argType = None
		elif arg.startswith('-'):
			if arg in ['-f', '-i', '-a', '-o', '-r']:
				argType = arg
			elif arg == '-s':
				spaces = True
			elif arg == '-S':
				spaces = False
			elif arg == '-j':
				joiners = True
			elif arg == '-J':
				joiners = False
			elif arg == '-w':
				webkitFix = True
			elif arg == '-W':
				webkitFix = False
			else:
				print(('Unknown option: %s' % arg), file=sys.stderr)
		else:
			fontFile = arg
	# Build feature files
	if fontFile is None:
		print('No source font provided', file=sys.stderr)
	else:
		gc = GlyphCollection(fontFile)
		gc.parseInfoFile(inputFile)
		gc.parseInfoFinish()
		gc.writeAsciiSequences(asciiFile, spaces, joiners, webkitFix)
		gc.writeFeatureFile(outputFile, rsubDepth)

if __name__ == '__main__':
	main(sys.argv[1:])
