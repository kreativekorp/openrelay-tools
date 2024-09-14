#!/usr/bin/env python

from __future__ import print_function
from pypuaa import ttfHeaderStruct, ttfTableStruct, PuaaTable, mapFromEntries, compilePUAA
import io
import os
import struct
import sys
import unicodedata


NAME = 0x6E616D65
CMAP = 0x636D6170
PUAA = 0x50554141


class NameEntry:
	def __init__(self, pid, psid, lang, id, length, offset):
		self.platformID = pid
		self.platformSpecificID = psid
		self.languageID = lang
		self.nameID = id
		self.length = length
		self.offset = offset
		if pid == 0 or pid == 2 or pid == 10:
			self.encoding = 'utf-16be'
			self.isEnglish = True
		elif pid == 3 and (psid == 1 or psid == 10):
			self.encoding = 'utf-16be'
			self.isEnglish = (lang == 1033)
		elif pid == 1 and psid == 0:
			self.encoding = 'macroman'
			self.isEnglish = (lang == 0)
		else:
			self.encoding = None
			self.isEnglish = False

	def decompile(self, data):
		self.data = data
		self.name = None if self.encoding is None else data.decode(self.encoding)


class CmapEntry:
	def __init__(self, pid, psid, offset):
		self.platformID = pid
		self.platformSpecificID = psid
		self.offset = offset
		if pid == 0 or pid == 2 or pid == 10:
			self.isMacRoman = False
			self.isUnicode = True
		elif pid == 3 and (psid == 1 or psid == 10):
			self.isMacRoman = False
			self.isUnicode = True
		elif pid == 1 and psid == 0:
			self.isMacRoman = True
			self.isUnicode = False
		else:
			self.isMacRoman = False
			self.isUnicode = False

	def decompile(self, format, length, language, data):
		self.format = format
		self.length = length
		self.language = language
		self.data = data
		if format == 0:
			self.entries = {}
			for i in range(0, len(data)):
				cp = ord(chr(i).decode('macroman'))
				self.entries[cp] = ord(data[i])
		elif format == 4:
			self.entries = []
			countX2 = struct.unpack('>H', data[0:2])[0]
			for i in range(0, countX2, 2):
				dp = i + 8
				stop = struct.unpack('>H', data[dp:dp+2])[0]
				dp += countX2 + 2
				start = struct.unpack('>H', data[dp:dp+2])[0]
				dp += countX2
				delta = struct.unpack('>H', data[dp:dp+2])[0]
				dp += countX2
				offset = struct.unpack('>H', data[dp:dp+2])[0]
				self.entries.append((start, stop, delta, offset, dp))
			self.min = min(e[0] for e in self.entries)
			self.max = max(e[1] for e in self.entries)
		elif format == 6:
			self.first, self.count = struct.unpack('>HH', data[0:4])
		elif format == 10:
			self.first, self.count = struct.unpack('>II', data[0:8])
		elif format == 12:
			self.entries = []
			count = struct.unpack('>I', data[0:4])[0]
			for i in range(0, count):
				dp = i * 12 + 4
				start, stop, glyph = struct.unpack('>III', data[dp:dp+12])
				self.entries.append((start, stop, glyph))
			self.min = min(e[0] for e in self.entries)
			self.max = max(e[1] for e in self.entries)

	def glyph(self, cp):
		if self.format == 0:
			if cp in self.entries:
				return self.entries[cp]
		elif self.format == 4:
			if cp >= self.min and cp <= self.max:
				for start, stop, delta, offset, dp in self.entries:
					if cp >= start and cp <= stop:
						if offset == 0:
							return (cp + delta) & 0xFFFF
						else:
							ip = dp + offset + ((cp - start) << 1)
							if ip < len(self.data):
								glyph = struct.unpack('>H', self.data[ip:ip+2])[0]
								if glyph > 0:
									return (glyph + delta) & 0xFFFF
		elif self.format == 6:
			i = cp - self.first
			if i >= 0 and i < self.count:
				dp = (i << 1) + 4
				return struct.unpack('>H', self.data[dp:dp+2])[0]
		elif self.format == 10:
			i = cp - self.first
			if i >= 0 and i < self.count:
				dp = (i << 1) + 8
				return struct.unpack('>H', self.data[dp:dp+2])[0]
		elif self.format == 12:
			if cp >= self.min and cp <= self.max:
				for start, stop, glyph in self.entries:
					if cp >= start and cp <= stop:
						return (glyph + (cp - start)) & 0xFFFF
		return 0

	def glyphs(self):
		if self.format == 0:
			for cp in self.entries:
				glyph = self.entries[cp]
				if glyph > 0:
					yield cp, glyph
		elif self.format == 4:
			for start, stop, delta, offset, dp in self.entries:
				for cp in range(start, stop + 1):
					if offset == 0:
						glyph = (cp + delta) & 0xFFFF
						if glyph > 0:
							yield cp, glyph
					else:
						ip = dp + offset + ((cp - start) << 1)
						if ip < len(self.data):
							glyph = struct.unpack('>H', self.data[ip:ip+2])[0]
							if glyph > 0:
								glyph = (glyph + delta) & 0xFFFF
								if glyph > 0:
									yield cp, glyph
		elif self.format == 6:
			for i in range(0, self.count):
				dp = (i << 1) + 4
				glyph = struct.unpack('>H', self.data[dp:dp+2])[0]
				if glyph > 0:
					yield self.first + i, glyph
		elif self.format == 10:
			for i in range(0, self.count):
				dp = (i << 1) + 8
				glyph = struct.unpack('>H', self.data[dp:dp+2])[0]
				if glyph > 0:
					yield self.first + i, glyph
		elif self.format == 12:
			for start, stop, glyph in self.entries:
				for cp in range(start, stop + 1):
					gid = (glyph + (cp - start)) & 0xFFFF
					if gid > 0:
						yield cp, gid


class TtfInfo:
	def __init__(self, path=None):
		self.names = None
		self.cmaps = None
		self.puaa = None
		if path is not None:
			self.read(path)

	def read(self, path):
		with open(path, 'rb') as fp:
			scaler, numTables, searchRange, entrySelector, rangeShift = ttfHeaderStruct.unpack(fp.read(12))
			tables = [ttfTableStruct.unpack(fp.read(16)) for i in range(0, numTables)]
			for tag, checksum, offset, length in tables:
				if tag == NAME:
					fp.seek(offset)
					nameFormat, numRecords, stringOffset = struct.unpack('>HHH', fp.read(6))
					self.names = [NameEntry(*struct.unpack('>HHHHHH', fp.read(12))) for i in range(0, numRecords)]
					for name in self.names:
						fp.seek(offset + stringOffset + name.offset)
						name.decompile(fp.read(name.length))
				elif tag == CMAP:
					fp.seek(offset)
					cmapFormat, numRecords = struct.unpack('>HH', fp.read(4))
					self.cmaps = [CmapEntry(*struct.unpack('>HHI', fp.read(8))) for i in range(0, numRecords)]
					for cmap in self.cmaps:
						fp.seek(offset + cmap.offset)
						cmapFormat, length = struct.unpack('>HH', fp.read(4))
						if cmapFormat < 8:
							language = struct.unpack('>H', fp.read(2))[0]
							data = fp.read(length - 6)
						elif cmapFormat < 14:
							length, language = struct.unpack('>II', fp.read(8))
							data = fp.read(length - 12)
						else:
							lengthLo = struct.unpack('>H', fp.read(2))[0]
							length = (length << 16) | lengthLo
							language = 0
							data = fp.read(length - 6)
						cmap.decompile(cmapFormat, length, language, data)
				elif tag == PUAA:
					fp.seek(offset)
					self.puaa = PuaaTable()
					self.puaa.decompile(fp.read(length))

	def bestName(self, id):
		for name in self.names:
			if name.nameID == id and name.isEnglish and name.encoding == 'utf-16be':
				return name
		for name in self.names:
			if name.nameID == id and name.isEnglish and name.encoding is not None:
				return name
		return None

	def bestCmap(self):
		for cmap in self.cmaps:
			if cmap.isUnicode and cmap.format == 12:
				return cmap
		for cmap in self.cmaps:
			if cmap.isUnicode and cmap.format == 4:
				return cmap
		return None

	def makeCharacterMap(self):
		cmap = self.bestCmap()
		if cmap is not None:
			return {cp: glyph for cp, glyph in cmap.glyphs()}
		return None


def readUCD(path=None, puaa=None):
	if path is None:
		path = os.path.normpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'unidata.ucd'))
	if puaa is None:
		puaa = PuaaTable()
	with open(path, 'rb') as fp:
		scaler, numTables, searchRange, entrySelector, rangeShift = ttfHeaderStruct.unpack(fp.read(12))
		tables = [ttfTableStruct.unpack(fp.read(16)) for i in range(0, numTables)]
		for tag, checksum, offset, length in tables:
			if tag == PUAA:
				fp.seek(offset)
				puaa.decompile(fp.read(length))
	return puaa


class BlockMap:
	def __init__(self, *args):
		self.blocks = {
			0x000000: 'Undefined (BMP)',
			0x010000: 'Undefined (SMP)',
			0x020000: 'Undefined (SIP)',
			0x030000: 'Undefined (TIP)',
			0x040000: 'Undefined (Plane 4)',
			0x050000: 'Undefined (Plane 5)',
			0x060000: 'Undefined (Plane 6)',
			0x070000: 'Undefined (Plane 7)',
			0x080000: 'Undefined (Plane 8)',
			0x090000: 'Undefined (Plane 9)',
			0x0A0000: 'Undefined (Plane 10)',
			0x0B0000: 'Undefined (Plane 11)',
			0x0C0000: 'Undefined (Plane 12)',
			0x0D0000: 'Undefined (Plane 13)',
			0x0E0000: 'Undefined (SSP)',
			0x0F0000: 'Undefined (SPUA-A)',
			0x100000: 'Undefined (SPUA-B)',
			0x110000: 'Invalid'
		}
		for arg in args:
			self.putAll(arg)

	def get(self, cp):
		return self.blocks[max(bcp for bcp in self.blocks.keys() if bcp <= cp)]

	def getAll(self):
		bcp = 0
		ecp = min(cp for cp in self.blocks.keys() if cp > bcp)
		yield bcp, ecp - 1, self.blocks[bcp]
		while ecp < 0x110000:
			bcp = ecp
			ecp = min(cp for cp in self.blocks.keys() if cp > bcp)
			yield bcp, ecp - 1, self.blocks[bcp]

	def put(self, bcp, ecp, block):
		self.blocks[ecp + 1] = self.get(ecp + 1)
		self.blocks[bcp] = block
		for cp in [cp for cp in self.blocks.keys() if bcp < cp <= ecp]:
			del self.blocks[cp]

	def putAll(self, ucd):
		if ucd is not None:
			st = ucd.subtable('Block')
			if st is not None and st.entries is not None:
				for b in st.entries:
					self.put(b.firstCodePoint, b.lastCodePoint, b.value)


def puaaPropertyMap(puaa, propertyName):
	if puaa is not None:
		subtable = puaa.subtable(propertyName)
		if subtable is not None:
			return mapFromEntries(subtable.entries)
	return None


def createReport(ucd, ttf, allChars=False):
	name = ttf.bestName(1)
	name = name.name if name is not None else None
	version = ttf.bestName(5)
	version = version.name if version is not None else None
	count = 0
	blocks = []
	blockMap = BlockMap(ucd, ttf.puaa)
	charMap = ttf.makeCharacterMap()
	charInfoProps = ['kkChartClipping', 'kkChartSource', 'kkChartAnnotation']
	charInfoMaps = {p: puaaPropertyMap(ttf.puaa, p) for p in charInfoProps}
	reportInfo = {p: (charInfoMaps[p] is not None) for p in charInfoProps}
	reportInfo['allChars'] = allChars
	ttfCcc = puaaPropertyMap(ttf.puaa, 'Canonical_Combining_Class')
	ucdCcc = puaaPropertyMap(ucd, 'Canonical_Combining_Class')
	ttfNames = puaaPropertyMap(ttf.puaa, 'Name')
	ucdNames = puaaPropertyMap(ucd, 'Name')
	for bcp, ecp, block in blockMap.getAll():
		chars = []
		for cp in range(bcp, ecp + 1):
			if (allChars or 0xE000 <= cp < 0xF900 or cp >= 0xF0000) and cp in charMap:
				charInfo = {
					p: (charInfoMaps[p][cp] if charInfoMaps[p] is not None and cp in charInfoMaps[p] else None)
					for p in charInfoProps
				}
				if ttfCcc is not None and cp in ttfCcc:
					charInfo['Canonical_Combining_Class'] = int(ttfCcc[cp])
				elif ucdCcc is not None and cp in ucdCcc:
					charInfo['Canonical_Combining_Class'] = int(ucdCcc[cp])
				else:
					charInfo['Canonical_Combining_Class'] = unicodedata.combining(u'%c' % cp)
				if ttfNames is not None and cp in ttfNames:
					chars.append((cp, ttfNames[cp], charInfo))
				elif ucdNames is not None and cp in ucdNames:
					chars.append((cp, ucdNames[cp], charInfo))
				else:
					pn = 'PRIVATE USE' if 0xE000 <= cp < 0xF900 or cp >= 0xF0000 else 'UNDEFINED'
					chars.append((cp, unicodedata.name(u'%c' % cp, '%s-%04X' % (pn, cp)), charInfo))
		if len(chars) > 0:
			count += len(chars)
			blocks.append((bcp, ecp, block, chars))
	return (name, version, count, blocks, reportInfo)


def printReportNTHTML(report, file=None):
	name, version, count, blocks, reportInfo = report
	print(u'<html lang="en">', file=file)
	print(u'<head>', file=file)
	print(u'<style>', file=file)
	print(u'* { margin: 0; padding: 0; }', file=file)
	print(u'body { margin: 1em; font-family: sans-serif; }', file=file)
	print(u'h3 { color: #639; }', file=file)
	print(u'th { padding: 1em 1em 2px 4px; text-align: left; }', file=file)
	print(u'td { padding: 2px 1em 2px 4px; text-align: left; }', file=file)
	print(u'.br, .cp { text-align: right; }', file=file)
	print(u'.br, .cp, .cg, .cs, .ca { white-space: nowrap; }', file=file)
	print(u'.cg { font-family: "%s"; font-size: 120%%; text-align: center; }' % name, file=file)
	print(u'.cg.clip { overflow: hidden; }', file=file)
	print(u'.cg.noclip { overflow: visible; }', file=file)
	print(u'.cs { font-size: 80%; background: #F2F2F2; color: #C6C; }', file=file)
	print(u'.ca { font-size: 80%; }', file=file)
	print(u'</style>', file=file)
	print(u'</head>', file=file)
	print(u'<body>', file=file)
	if reportInfo['allChars']:
		print(u'<h3>%s %s - %d characters</h3>' % (name, version, count), file=file)
	else:
		print(u'<h3>%s %s - %d characters in the Private Use Areas</h3>' % (name, version, count), file=file)
	print(u'<table border="0" cellpadding="0" cellspacing="0">', file=file)
	for bcp, ecp, block, chars in blocks:
		print(u'<thead>', file=file)
		print(u'<tr class="bh">', file=file)
		print(u'<th class="br">%04X..%04X</th>' % (bcp, ecp), file=file)
		print(u'<th class="bg"></th>', file=file)
		if reportInfo['kkChartSource']:
			print(u'<th class="bs"></th>', file=file)
		print(u'<th class="bn">%s - %d characters</th>' % (block, len(chars)), file=file)
		if reportInfo['kkChartAnnotation']:
			print(u'<th class="ba"></th>', file=file)
		print(u'</tr>', file=file)
		print(u'</thead>', file=file)
		print(u'<tbody>', file=file)
		for cp, name, charInfo in chars:
			print(u'<tr class="ch">', file=file)
			print(u'<td class="cp">%04X</td>' % cp, file=file)
			cgClass = (
				u'cg' if charInfo['kkChartClipping'] is None else
				u'cg clip' if charInfo['kkChartClipping'] in ['Y', 'y'] else
				u'cg noclip' if charInfo['kkChartClipping'] in ['N', 'n'] else
				u'cg'
			)
			cgContent = (
				# (u'&#%d;' % cp) if charInfo['Canonical_Combining_Class'] is None else
				# (u'&#9676;&#%d;&#9676;' % cp) if 233 <= charInfo['Canonical_Combining_Class'] <= 234 else
				# (u'&#9676;&#%d;' % cp) if charInfo['Canonical_Combining_Class'] > 0 else
				(u'&#%d;' % cp)
			)
			print(u'<td class="%s">%s</td>' % (cgClass, cgContent), file=file)
			if reportInfo['kkChartSource']:
				print(u'<td class="cs">%s</td>' % (charInfo['kkChartSource'] if charInfo['kkChartSource'] is not None else ''), file=file)
			print(u'<td class="cn">%s</td>' % name, file=file)
			if reportInfo['kkChartAnnotation']:
				print(u'<td class="ca">%s</td>' % (charInfo['kkChartAnnotation'] if charInfo['kkChartAnnotation'] is not None else ''), file=file)
			print(u'</tr>', file=file)
		print(u'</tbody>', file=file)
	print(u'</table>', file=file)
	print(u'</body>', file=file)
	print(u'</html>', file=file)


def main(args):
	def printHelp():
		print()
		print('puaabook - Produce documentation for private use characters in TrueType files.')
		print()
		print('  -u <path>     Specify file or directory for Unicode character properties.')
		print('  -d <path>     Specify file or directory for private use character properties.')
		print('  -i <path>     Specify source TrueType file.')
		print('  -o <path>     Specify destination documentation file.')
		print('  -U            Process arguments as if prefixed by -u.')
		print('  -D            Process arguments as if prefixed by -d.')
		print('  -I            Process arguments as if prefixed by -i.')
		print('  -O            Process arguments as if prefixed by -o.')
		print('  --            Process remaining arguments as file names.')
		print()
	if not args:
		printHelp()
		return
	ucdFiles = []
	dataFiles = []
	inputFiles = []
	outputFiles = []
	defaultList = inputFiles
	parsingOptions = True
	allChars = False
	argi = 0
	while argi < len(args):
		arg = args[argi]
		argi += 1
		if parsingOptions and arg.startswith('-'):
			if arg == '--':
				parsingOptions = False
			elif arg == '-u' and argi < len(args):
				ucdFiles.append(args[argi])
				argi += 1
			elif arg == '-d' and argi < len(args):
				dataFiles.append(args[argi])
				argi += 1
			elif arg == '-i' and argi < len(args):
				inputFiles.append(args[argi])
				argi += 1
			elif arg == '-o' and argi < len(args):
				outputFiles.append(args[argi])
				argi += 1
			elif arg == '-U':
				defaultList = ucdFiles
			elif arg == '-D':
				defaultList = dataFiles
			elif arg == '-I':
				defaultList = inputFiles
			elif arg == '-O':
				defaultList = outputFiles
			elif arg == '-a':
				allChars = True
			elif arg == '-p':
				allChars = False
			elif arg == '--help':
				printHelp()
				return
			else:
				print('Unknown option: %s' % arg)
				return
		else:
			defaultList.append(arg)
	if not inputFiles:
		print('No input files specified.')
	elif len(inputFiles) > 1:
		print('Too many input files.')
	else:
		ucd = None
		if ucdFiles:
			for ucdFile in ucdFiles:
				if ucdFile.lower().endswith('.txt') or os.path.isdir(ucdFile):
					ucd = compilePUAA([ucdFile], puaa=ucd, assumeUnihan=os.path.isfile(ucdFile))
				else:
					ucd = readUCD(ucdFile, puaa=ucd)
		else:
			try:
				ucd = readUCD(puaa=ucd)
			except IOError:
				pass
		ttf = TtfInfo(inputFiles[0])
		if dataFiles:
			for dataFile in dataFiles:
				if dataFile.lower().endswith('.txt') or os.path.isdir(dataFile):
					ttf.puaa = compilePUAA([dataFile], puaa=ttf.puaa, assumeUnihan=os.path.isfile(dataFile))
				else:
					ttf.puaa = readUCD(dataFile, puaa=ttf.puaa)
		report = createReport(ucd, ttf, allChars=allChars)
		if outputFiles:
			for outputFile in outputFiles:
				with io.open(outputFile, mode='w', encoding='utf8') as f:
					printReportNTHTML(report, file=f)
		else:
			printReportNTHTML(report)


if __name__ == '__main__':
	main(sys.argv[1:])
