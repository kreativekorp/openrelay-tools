#!/usr/bin/env python

from __future__ import print_function
from bitset import BitSet
import io
import os
import re
import struct
import sys


PUAA = 0x50554141
HEAD = 0x68656164
CHKSUM = 0xB1B0AFBA
INT_MIN = 0x80000000
UINT_MAX = 0xFFFFFFFF
NULLS = '\x00\x00\x00\x00'.encode('utf8')

SINGLE = 1
MULTIPLE = 2
BOOLEAN = 3
DECIMAL = 4
HEXADECIMAL = 5
HEXMULTIPLE = 6
HEXSEQUENCE = 7
CASEMAPPING = 8
NAMEALIAS = 9


class PuaaEntry():
	def __init__(self, firstCodePoint, lastCodePoint):
		self.firstCodePoint = firstCodePoint
		self.lastCodePoint = lastCodePoint

	def contains(self, cp):
		return self.firstCodePoint <= cp <= self.lastCodePoint

	def propertyValue(self, cp):
		raise KeyError('%04X' % cp)

class SingleEntry(PuaaEntry):
	def __init__(self, firstCodePoint, lastCodePoint, value):
		PuaaEntry.__init__(self, firstCodePoint, lastCodePoint)
		self.value = value

	def propertyValue(self, cp):
		return self.value

class MultipleEntry(PuaaEntry):
	def __init__(self, firstCodePoint, lastCodePoint, values):
		PuaaEntry.__init__(self, firstCodePoint, lastCodePoint)
		self.values = values

	def propertyValue(self, cp):
		return self.values[cp - self.firstCodePoint]

class BooleanEntry(PuaaEntry):
	def __init__(self, firstCodePoint, lastCodePoint, value):
		PuaaEntry.__init__(self, firstCodePoint, lastCodePoint)
		self.value = value

	def propertyValue(self, cp):
		return 'Y' if self.value else 'N'

class DecimalEntry(PuaaEntry):
	def __init__(self, firstCodePoint, lastCodePoint, value):
		PuaaEntry.__init__(self, firstCodePoint, lastCodePoint)
		self.value = value

	def propertyValue(self, cp):
		return '%d' % self.value

class HexadecimalEntry(PuaaEntry):
	def __init__(self, firstCodePoint, lastCodePoint, value):
		PuaaEntry.__init__(self, firstCodePoint, lastCodePoint)
		self.value = value

	def propertyValue(self, cp):
		return '%04X' % self.value

class HexMultipleEntry(PuaaEntry):
	def __init__(self, firstCodePoint, lastCodePoint, values):
		PuaaEntry.__init__(self, firstCodePoint, lastCodePoint)
		self.values = values

	def propertyValue(self, cp):
		return '%04X' % self.values[cp - self.firstCodePoint]

class HexSequenceEntry(PuaaEntry):
	def __init__(self, firstCodePoint, lastCodePoint, value):
		PuaaEntry.__init__(self, firstCodePoint, lastCodePoint)
		self.value = value

	def propertyValue(self, cp):
		return ' '.join('%04X' % value for value in self.value)

class CaseMappingEntry(PuaaEntry):
	def __init__(self, firstCodePoint, lastCodePoint, mapping, condition=None):
		PuaaEntry.__init__(self, firstCodePoint, lastCodePoint)
		self.mapping = mapping
		self.condition = condition

	def propertyValue(self, cp):
		v = ' '.join('%04X' % value for value in self.mapping)
		return '%s; %s' % (v, self.condition) if self.condition else v

class NameAliasEntry(PuaaEntry):
	def __init__(self, firstCodePoint, lastCodePoint, alias, aliasType):
		PuaaEntry.__init__(self, firstCodePoint, lastCodePoint)
		self.alias = alias
		self.aliasType = aliasType

	def propertyValue(self, cp):
		return '%s;%s' % (self.alias, self.aliasType)

class PuaaSubtable:
	def __init__(self, propertyName):
		self.propertyName = propertyName
		self.entries = []

	def propertyValue(self, cp):
		returnValue = None
		for entry in self.entries:
			if entry.contains(cp):
				value = entry.propertyValue(cp)
				if value is not None:
					if returnValue is None:
						returnValue = value
					else:
						returnValue += value
		return returnValue

	def isSortable(self):
		codePoints = BitSet()
		for entry in self.entries:
			if codePoints.getAny(entry.firstCodePoint, entry.lastCodePoint):
				return False
			else:
				codePoints.setAll(entry.firstCodePoint, entry.lastCodePoint)
		return True

	def sort(self):
		if self.isSortable():
			self.entries.sort(key=lambda e: (e.firstCodePoint, e.lastCodePoint))


def checkSigned32(v):
	if -INT_MIN <= v < INT_MIN:
		return v
	raise OverflowError(v)

def checkUnsigned32(v):
	if 0 <= v <= UINT_MAX:
		return v
	raise OverflowError(v)

def signedToUnsigned32(v):
	if 0 <= v < INT_MIN:
		return v
	if -INT_MIN <= v < 0:
		return v + INT_MIN + INT_MIN
	raise OverflowError(v)

def unsignedToSigned32(v):
	if 0 <= v < INT_MIN:
		return v
	if INT_MIN <= v <= UINT_MAX:
		return v - INT_MIN - INT_MIN
	raise OverflowError(v)

def minify3(d):
	if d is None:
		return None
	if len(d) > 4:
		return None
	v = INT_MIN
	if len(d) > 3:
		if d[3] & 0x80:
			return None
		v |= (d[3] & 0x7F) << 0
	if len(d) > 2:
		if d[2] & 0x80:
			return None
		v |= (d[2] & 0x7F) << 8
	if len(d) > 1:
		if d[1] & 0x80:
			return None
		v |= (d[1] & 0x7F) << 16
	if len(d) > 0:
		if d[0] & 0x80:
			return None
		v |= (d[0] & 0x7F) << 24
	return v

def minify2(d):
	if d is None:
		return None
	if len(d) > 4:
		return None
	v = INT_MIN
	if len(d) > 3:
		if ord(d[3]) & 0x80:
			return None
		v |= (ord(d[3]) & 0x7F) << 0
	if len(d) > 2:
		if ord(d[2]) & 0x80:
			return None
		v |= (ord(d[2]) & 0x7F) << 8
	if len(d) > 1:
		if ord(d[1]) & 0x80:
			return None
		v |= (ord(d[1]) & 0x7F) << 16
	if len(d) > 0:
		if ord(d[0]) & 0x80:
			return None
		v |= (ord(d[0]) & 0x7F) << 24
	return v

def minifyFn():
	try:
		if '!'.encode('utf8')[0] & 1:
			return minify3
	except:
		pass
	try:
		if ord('!'.encode('utf8')[0]) & 1:
			return minify2
	except:
		pass
	raise AssertionError('minify broken')

minify = minifyFn()

byteStruct = struct.Struct('>B')
shortStruct = struct.Struct('>H')
intStruct = struct.Struct('>I')
headerStruct = struct.Struct('>HH')
subtableStruct = struct.Struct('>II')
entryStruct = struct.Struct('>BBHHI')
ttfHeaderStruct = struct.Struct('>IHHHH')
ttfTableStruct = struct.Struct('>IIII')

class PuaaTable:
	def __init__(self):
		self.subtables = []

	def subtable(self, propertyName, create=False):
		for st in self.subtables:
			if st.propertyName == propertyName:
				return st
		if create:
			st = PuaaSubtable(propertyName)
			self.subtables.append(st)
			return st
		return None

	def propertyValue(self, propertyName, cp):
		for st in self.subtables:
			if st.propertyName == propertyName:
				return st.propertyValue(cp)
		return None

	def removeEmpty(self):
		self.subtables = [st for st in self.subtables if st.entries]

	def sort(self):
		self.subtables.sort(key=lambda st: st.propertyName)
		for st in self.subtables:
			st.sort()

	def compile(self):
		self.removeEmpty()
		self.sort()

		# Calculate subtable header values.
		subtableHeaderOffset = []
		p = [4 + len(self.subtables) * 8]
		for st in self.subtables:
			subtableHeaderOffset.append(p[0])
			p[0] += 2 + len(st.entries) * 10

		# Calculate entry header values.
		entryType = []
		entryData = []
		valueCount = []
		valueData = []
		for st in self.subtables:
			subEntryType = []
			subEntryData = []
			subValueCount = []
			subValueData = []
			def subAppend(et, ed, vc, vd):
				subEntryType.append(et)
				subEntryData.append(ed)
				subValueCount.append(vc)
				subValueData.append(vd)
				if vc is not None:
					p[0] += 2 + vc * 4
			for entry in st.entries:
				if isinstance(entry, SingleEntry):
					subAppend(SINGLE, None, None, None)
				if isinstance(entry, MultipleEntry):
					subAppend(MULTIPLE, p[0], len(entry.values), None)
				if isinstance(entry, BooleanEntry):
					subAppend(BOOLEAN, UINT_MAX if entry.value else 0, None, None)
				if isinstance(entry, DecimalEntry):
					subAppend(DECIMAL, signedToUnsigned32(entry.value), None, None)
				if isinstance(entry, HexadecimalEntry):
					subAppend(HEXADECIMAL, checkUnsigned32(entry.value), None, None)
				if isinstance(entry, HexMultipleEntry):
					subAppend(HEXMULTIPLE, p[0], len(entry.values), entry.values)
				if isinstance(entry, HexSequenceEntry):
					subAppend(HEXSEQUENCE, p[0], len(entry.value), entry.value)
				if isinstance(entry, CaseMappingEntry):
					subAppend(CASEMAPPING, p[0], len(entry.mapping) + 1, None)
				if isinstance(entry, NameAliasEntry):
					subAppend(NAMEALIAS, p[0], 2, None)
			entryType.append(subEntryType)
			entryData.append(subEntryData)
			valueCount.append(subValueCount)
			valueData.append(subValueData)

		# Create string table.
		stringTable = {}
		stringData = []
		def strAddr(s, forceFull=False):
			if s is None:
				return 0
			if s in stringTable:
				return stringTable[s]
			d = s.encode('utf8')
			if not forceFull:
				v = minify(d)
				if v is not None:
					return v
			sp = p[0]
			stringTable[s] = sp
			stringData.append(d)
			p[0] += len(d) + 1
			return sp

		# Calculate property name offsets.
		propertyNameOffset = [strAddr(st.propertyName, True) for st in self.subtables]

		# Calculate string data offsets.
		for i in range(0, len(self.subtables)):
			for j in range(0, len(self.subtables[i].entries)):
				entry = self.subtables[i].entries[j]
				if isinstance(entry, SingleEntry):
					entryData[i][j] = strAddr(entry.value)
				if isinstance(entry, MultipleEntry):
					valueData[i][j] = [strAddr(value) for value in entry.values]
				if isinstance(entry, CaseMappingEntry):
					valueData[i][j] = entry.mapping + [strAddr(entry.condition)]
				if isinstance(entry, NameAliasEntry):
					s1 = strAddr(entry.alias)
					s2 = strAddr(entry.aliasType)
					valueData[i][j] = [s1, s2]

		# Write table header.
		puaa = [headerStruct.pack(1, len(self.subtables))]
		for i in range(0, len(self.subtables)):
			puaa.append(subtableStruct.pack(propertyNameOffset[i], subtableHeaderOffset[i]))

		# Write subtable headers.
		for i in range(0, len(self.subtables)):
			puaa.append(shortStruct.pack(len(self.subtables[i].entries)))
			for j in range(0, len(self.subtables[i].entries)):
				entry = self.subtables[i].entries[j]
				puaa.append(entryStruct.pack(
					entryType[i][j],
					entry.firstCodePoint >> 16,
					entry.firstCodePoint & 0xFFFF,
					entry.lastCodePoint & 0xFFFF,
					entryData[i][j]
				))

		# Write entry data.
		for i in range(0, len(self.subtables)):
			for j in range(0, len(self.subtables[i].entries)):
				if valueData[i][j] is not None:
					puaa.append(shortStruct.pack(valueCount[i][j]))
					for d in valueData[i][j]:
						puaa.append(intStruct.pack(d))

		# Write string data.
		for d in stringData:
			puaa.append(byteStruct.pack(len(d)))
			puaa.append(d)

		return ''.encode('utf8').join(puaa)

	def decompile(self, data):
		def getStr(offset):
			if offset & INT_MIN:
				d = [(offset >> ((3 - i) << 3)) & 0x7F for i in range(0, 4)]
				return ''.join(chr(b) for b in d if b)
			if offset:
				try:
					return data[(offset+1):(offset+1+data[offset])].decode('utf8')
				except:
					return data[(offset+1):(offset+1+ord(data[offset]))].decode('utf8')
			return None

		def getInts(offset):
			n = shortStruct.unpack(data[offset:(offset+2)])[0]
			return [intStruct.unpack(data[(offset+2+i*4):(offset+6+i*4)])[0] for i in range(0, n)]

		# Read table header.
		version, propertyCount = headerStruct.unpack(data[0:4])
		if version != 1:
			raise ValueError('unknown PUAA version %d' % version)

		# Read subtables.
		for i in range(0, propertyCount):
			pno, sho = subtableStruct.unpack(data[(4+i*8):(12+i*8)])
			entryCount = shortStruct.unpack(data[sho:(sho+2)])[0]
			st = PuaaSubtable(getStr(pno))

			# Read entries.
			for j in range(0, entryCount):
				et, p, f, l, ed = entryStruct.unpack(data[(sho+2+j*10):(sho+12+j*10)])
				firstCodePoint = (p << 16) | f
				lastCodePoint = (p << 16) | l
				if et == SINGLE:
					entry = SingleEntry(firstCodePoint, lastCodePoint, getStr(ed))
					st.entries.append(entry)
				if et == MULTIPLE:
					values = [getStr(v) for v in getInts(ed)]
					entry = MultipleEntry(firstCodePoint, lastCodePoint, values)
					st.entries.append(entry)
				if et == BOOLEAN:
					entry = BooleanEntry(firstCodePoint, lastCodePoint, ed != 0)
					st.entries.append(entry)
				if et == DECIMAL:
					entry = DecimalEntry(firstCodePoint, lastCodePoint, unsignedToSigned32(ed))
					st.entries.append(entry)
				if et == HEXADECIMAL:
					entry = HexadecimalEntry(firstCodePoint, lastCodePoint, checkUnsigned32(ed))
					st.entries.append(entry)
				if et == HEXMULTIPLE:
					entry = HexMultipleEntry(firstCodePoint, lastCodePoint, getInts(ed))
					st.entries.append(entry)
				if et == HEXSEQUENCE:
					entry = HexSequenceEntry(firstCodePoint, lastCodePoint, getInts(ed))
					st.entries.append(entry)
				if et == CASEMAPPING:
					values = getInts(ed)
					entry = CaseMappingEntry(firstCodePoint, lastCodePoint, values[0:-1], getStr(values[-1]))
					st.entries.append(entry)
				if et == NAMEALIAS:
					values = [getStr(v) for v in getInts(ed)]
					entry = NameAliasEntry(firstCodePoint, lastCodePoint, values[0], values[1])
					st.entries.append(entry)

			self.subtables.append(st)


def readPUAA(path, verbose=False):
	if verbose:
		print('Decompiling from %s...' % os.path.basename(path))
	fp = open(path, 'rb')
	scaler, numTables, searchRange, entrySelector, rangeShift = ttfHeaderStruct.unpack(fp.read(12))
	tables = [ttfTableStruct.unpack(fp.read(16)) for i in range(0, numTables)]
	for tag, checksum, offset, length in tables:
		if tag == PUAA:
			table = PuaaTable()
			fp.seek(offset)
			data = fp.read(length)
			table.decompile(data)
			fp.close()
			return table
	fp.close()
	if verbose:
		print('Warning: No PUAA table found.')
	return None

def testPUAA(path, verbose=False):
	if verbose:
		print('Decompiling from %s...' % os.path.basename(path))
	fp = open(path, 'rb')
	scaler, numTables, searchRange, entrySelector, rangeShift = ttfHeaderStruct.unpack(fp.read(12))
	tables = [ttfTableStruct.unpack(fp.read(16)) for i in range(0, numTables)]
	for tag, checksum, offset, length in tables:
		if tag == PUAA:
			table = PuaaTable()
			fp.seek(offset)
			data = fp.read(length)
			table.decompile(data)
			fp.close()
			comp = table.compile()
			if verbose:
				print('PASS' if data == comp else 'FAIL')
			return (table, data, comp)
	fp.close()
	if verbose:
		print('Warning: No PUAA table found.')
	return (None, None, None)

def chksum(data):
	cs = 0
	nl = len(data) ^ (len(data) & 3)
	for i in range(0, nl, 4):
		cs += intStruct.unpack(data[i:(i+4)])[0]
		cs &= UINT_MAX
	for i in range(nl, len(data)):
		cs += byteStruct.unpack(data[i:(i+1)])[0] << (((i & 3) ^ 3) << 3)
		cs &= UINT_MAX
	return cs

def writePUAA(inpath, puaa, outpath, verbose=False):
	# Gather tables (including the PUAA table).
	scaler = PUAA
	newTables = []
	if inpath is not None:
		if verbose:
			print('Copying tables from %s...' % os.path.basename(inpath))
		fp = open(inpath, 'rb')
		scaler, numTables, searchRange, entrySelector, rangeShift = ttfHeaderStruct.unpack(fp.read(12))
		tables = [ttfTableStruct.unpack(fp.read(16)) for i in range(0, numTables)]
		for tag, checksum, offset, length in tables:
			if tag == PUAA:
				continue
			fp.seek(offset)
			data = fp.read(length)
			if tag == HEAD:
				# Clear the whole-file checksum in the 'head' table.
				data = data[0:8] + NULLS[0:4] + data[12:]
			td = [tag, checksum, offset, data]
			newTables.append(td)
		fp.close()
	if puaa is not None:
		if verbose:
			print('Compiling PUAA table...')
		data = puaa.compile()
		td = [PUAA, chksum(data), UINT_MAX, data]
		newTables.append(td)
	if verbose:
		print('Compiling to %s...' % os.path.basename(outpath))

	# Calculate header values.
	numTables = len(newTables)
	searchRange = 1 << 30
	entrySelector = 30
	while searchRange > numTables:
		searchRange >>= 1
		entrySelector -= 1
	searchRange <<= 4
	rangeShift = (numTables << 4) - searchRange

	# Calculate offsets.
	checksumLoc = 0
	currentLoc = 12 + (numTables << 4)
	newTables.sort(key=lambda td: td[2])
	for i in range(0, numTables):
		newTables[i][2] = currentLoc
		if newTables[i][0] == HEAD:
			# Note where the whole-file checksum ends up.
			checksumLoc = currentLoc + 8
		currentLoc += len(newTables[i][3])
		while currentLoc & 3:
			currentLoc += 1

	# Compile.
	ttf = [ttfHeaderStruct.pack(scaler, numTables, searchRange, entrySelector, rangeShift)]
	newTables.sort(key=lambda td: td[0])
	for tag, checksum, offset, data in newTables:
		ttf.append(ttfTableStruct.pack(tag, checksum, offset, len(data)))
	newTables.sort(key=lambda td: td[2])
	for tag, checksum, offset, data in newTables:
		ttf.append(data)
		if len(data) & 3:
			ttf.append(NULLS[(len(data)&3):4])
	data = ''.encode('utf8').join(ttf)
	if checksumLoc:
		# Update the whole-file checksum in the 'head' table.
		checksum = intStruct.pack((CHKSUM - chksum(data)) & UINT_MAX)
		data = data[0:checksumLoc] + checksum + data[(checksumLoc+4):]

	fp = open(outpath, 'wb')
	fp.write(data)
	fp.close()


def splitLine(s):
	s = s.split('#')[0].strip()
	return s.split(';') if s else None

def splitRange(s):
	ep = re.split('[.]+', s)
	start = int(ep[0].strip(), 16)
	if len(ep) < 2:
		return (start, start)
	end = int(ep[1].strip(), 16)
	return (start, end)

def joinRange(entry):
	if entry.firstCodePoint == entry.lastCodePoint:
		return '%04X' % entry.firstCodePoint
	else:
		return '%04X..%04X' % (entry.firstCodePoint, entry.lastCodePoint)

def naturalSortKey(s, _nsre=re.compile('([0-9]+)')):
	return [int(t) if t.isdigit() else t.lower() for t in _nsre.split(s)]


def appendToEntry(entry, cp, value):
	if entry is None:
		return False
	if (entry.lastCodePoint & 0xFFFF) == 0xFFFF:
		return False
	if (entry.lastCodePoint + 1) != cp:
		return False
	if isinstance(entry, SingleEntry):
		if entry.value == value:
			entry.lastCodePoint += 1
			return True
		return False
	if isinstance(entry, MultipleEntry):
		entry.values.append(value)
		entry.lastCodePoint += 1
		return True
	if isinstance(entry, BooleanEntry):
		if entry.value == value:
			entry.lastCodePoint += 1
			return True
		return False
	if isinstance(entry, DecimalEntry):
		if entry.value == value:
			entry.lastCodePoint += 1
			return True
		return False
	if isinstance(entry, HexadecimalEntry):
		if entry.value == value:
			entry.lastCodePoint += 1
			return True
		return False
	if isinstance(entry, HexMultipleEntry):
		entry.values.append(value)
		entry.lastCodePoint += 1
		return True
	if isinstance(entry, HexSequenceEntry):
		if entry.value == value:
			entry.lastCodePoint += 1
			return True
		return False
	return False

def sortedMap(m):
	items = [e for e in m.items() if e[1] is not None and e[1] != '' and e[1] != b'' and e[1] != u'']
	items.sort(key=lambda e: e[0])
	return items

def __runsFromMap(m, S):
	runs = []
	currentRun = None
	for cp, value in sortedMap(m):
		if not appendToEntry(currentRun, cp, value):
			currentRun = S(cp, cp, value)
			runs.append(currentRun)
	return runs

def __entriesFromRuns(runs, M, S):
	entries = []
	currentEntry = None
	for run in runs:
		if run.firstCodePoint != run.lastCodePoint:
			currentEntry = None
			entries.append(run)
		elif not appendToEntry(currentEntry, run.firstCodePoint, run.value):
			currentEntry = M(run.firstCodePoint, run.lastCodePoint, [run.value])
			entries.append(currentEntry)
	for i in range(0, len(entries)):
		if entries[i].firstCodePoint == entries[i].lastCodePoint:
			entries[i] = S(entries[i].firstCodePoint, entries[i].lastCodePoint, entries[i].values[0])
	return entries

def __entriesFromMap(m, S):
	entries = []
	currentEntry = None
	for cp, value in sortedMap(m):
		if not appendToEntry(currentEntry, cp, value):
			currentEntry = S(cp, cp, value)
			entries.append(currentEntry)
	return entries

def entriesFromStringMap(m):
	runs = __runsFromMap(m, SingleEntry)
	return __entriesFromRuns(runs, MultipleEntry, SingleEntry)

def entriesFromBooleanMap(m):
	return __entriesFromMap(m, BooleanEntry)

def entriesFromDecimalMap(m):
	return __entriesFromMap(m, DecimalEntry)

def entriesFromDecimalStringMap(m):
	entries = []
	currentEntry = None
	for cp, sv in sortedMap(m):
		try:
			value = checkSigned32(int(sv))
			if ('%d' % value) != sv:
				return None
			if not appendToEntry(currentEntry, cp, value):
				currentEntry = DecimalEntry(cp, cp, value)
				entries.append(currentEntry)
		except:
			return None
	return entries

def entriesFromHexadecimalMap(m):
	runs = __runsFromMap(m, HexadecimalEntry)
	return __entriesFromRuns(runs, HexMultipleEntry, HexadecimalEntry)

def entriesFromHexadecimalStringMap(m):
	runs = []
	currentRun = None
	for cp, sv in sortedMap(m):
		try:
			value = checkUnsigned32(int(sv, 16))
			if ('%04X' % value) != sv:
				return None
			if not appendToEntry(currentRun, cp, value):
				currentRun = HexadecimalEntry(cp, cp, value)
				runs.append(currentRun)
		except:
			return None
	return __entriesFromRuns(runs, HexMultipleEntry, HexadecimalEntry)

def entriesFromHexSequenceMap(m):
	return __entriesFromMap(m, HexSequenceEntry)


def splitName(s, _snre=re.compile('[\\w"#$%&\'()*<>@\\[\\]_{}]*[^\\s\\w"#$%&\'()*<>@\\[\\]_{}]*\\s*', re.U)):
	return [p for p in _snre.findall(s) if p]

def sortedNameMap(m):
	items = [(e[0], splitName(e[1])) for e in m.items() if e[1] is not None and e[1] != '' and e[1] != b'' and e[1] != u'']
	items.sort(key=lambda e: e[0])
	return items

def entriesFromNameMap(m):
	items = sortedNameMap(m)

	# Create entries for runs of common prefixes.
	prefixes = []
	while True:
		newPrefixes = []
		o, i, n = 0, 0, len(items)
		while o < n:
			firstItem = items[i]
			i += 1
			if firstItem[1]:
				# Create an entry for the first item's prefix.
				entry = SingleEntry(firstItem[0], firstItem[0], firstItem[1][0])
				# Extend the entry for subsequent items with the same prefix.
				while i < n and items[i][1] and appendToEntry(entry, items[i][0], items[i][1][0]):
					i += 1
				# If there were subsequent items, add an entry and remove the prefix.
				if entry.firstCodePoint != entry.lastCodePoint:
					newPrefixes.append(entry)
					while o < i:
						items[o][1].pop(0)
						o += 1
			o = i
		if newPrefixes:
			prefixes = prefixes + newPrefixes
		else:
			break

	# Create entries for runs of common suffixes.
	suffixes = []
	while True:
		newSuffixes = []
		o, i, n = 0, 0, len(items)
		while o < n:
			firstItem = items[i]
			i += 1
			if firstItem[1]:
				# Create an entry for the first item's suffix.
				entry = SingleEntry(firstItem[0], firstItem[0], firstItem[1][-1])
				# Extend the entry for subsequent items with the same suffix.
				while i < n and items[i][1] and appendToEntry(entry, items[i][0], items[i][1][-1]):
					i += 1
				# If there were subsequent items, add an entry and remove the suffix.
				if entry.firstCodePoint != entry.lastCodePoint:
					newSuffixes.append(entry)
					while o < i:
						items[o][1].pop(-1)
						o += 1
			o = i
		if newSuffixes:
			suffixes = newSuffixes + suffixes
		else:
			break

	# Add remaining name fragments.
	# There are two maps here because some values of the kDefinition
	# property in the Unihan database are longer than 255 bytes.
	# (The split is done in UTF-16 to match the Java implementation.)
	remainder1 = {}
	remainder2 = {}
	for item in items:
		if item[1]:
			value = ''.join(item[1])
			if len(value.encode('utf8')) > 255:
				v = value.encode('utf-16be')
				h = len(v) >> 2
				try:
					if (v[h*2] & 0xFC) == 0xDC:
						h += 1
				except:
					if (ord(v[h*2]) & 0xFC) == 0xDC:
						h += 1
				remainder1[item[0]] = v[0:(h*2)].decode('utf-16be')
				remainder2[item[0]] = v[(h*2):].decode('utf-16be')
			else:
				remainder1[item[0]] = value

	return prefixes + entriesFromStringMap(remainder1) + entriesFromStringMap(remainder2) + suffixes


def mapFromEntries(entries):
	m = {}
	for entry in entries:
		for cp in range(entry.firstCodePoint, entry.lastCodePoint+1):
			value = entry.propertyValue(cp)
			if value is not None:
				if cp in m:
					m[cp] += value
				else:
					m[cp] = value
	return m

def runsFromEntries(entries):
	m = sortedMap(mapFromEntries(entries))
	runs = []
	currentRun = None
	for cp, value in m:
		if not appendToEntry(currentRun, cp, value):
			currentRun = SingleEntry(cp, cp, value)
			runs.append(currentRun)
	return runs


class PuaaCodec:
	def __init__(self, fileName, propertyNames):
		self.fileName = fileName
		self.propertyNames = propertyNames

	def compile(self, puaa, f):
		raise NotImplementedError('must override compile()')

	def decompile(self, puaa, f):
		raise NotImplementedError('must override decompile()')

class PuaaCategoryCodec(PuaaCodec):
	def __init__(self, fileName, propertyName, propertyValues):
		PuaaCodec.__init__(self, fileName, [propertyName])
		self.propertyName = propertyName
		self.propertyValues = propertyValues

	def compile(self, puaa, f):
		values = {}
		for line in f:
			fields = splitLine(line)
			if fields is None or len(fields) < 2:
				continue
			try:
				fcp, lcp = splitRange(fields[0])
				v = fields[1].strip()
				for cp in range(fcp, lcp+1):
					values[cp] = v
			except:
				pass
		puaa.subtable(self.propertyName, True).entries += entriesFromStringMap(values)

	def decompile(self, puaa, f):
		values = puaa.subtable(self.propertyName, False)
		if values is None or not values.entries:
			return
		runs = runsFromEntries(values.entries)
		runs.sort(key=lambda e: (self.propertyValues.index(e.value), e.value, e.firstCodePoint, e.lastCodePoint))
		for run in runs:
			print(u'%-14s; %s' % (joinRange(run), run.value), file=f)

class PuaaPropListCodec(PuaaCodec):
	def __init__(self, fileName, propertyNames):
		PuaaCodec.__init__(self, fileName, propertyNames)

	def compile(self, puaa, f):
		props = {}
		for line in f:
			fields = splitLine(line)
			if fields is None or len(fields) < 2:
				continue
			try:
				fcp, lcp = splitRange(fields[0])
				prop = fields[1].strip()
				if prop not in props:
					props[prop] = {}
				for cp in range(fcp, lcp+1):
					props[prop][cp] = True
			except:
				pass
		for prop, m in props.items():
			puaa.subtable(prop, True).entries += entriesFromBooleanMap(m)

	def decompile(self, puaa, f):
		for prop in self.propertyNames:
			props = puaa.subtable(prop, False)
			if props is None or not props.entries:
				continue
			for run in runsFromEntries(props.entries):
				if run.value == 'Y':
					print(u'%-14s; %s' % (joinRange(run), prop), file=f)

class PuaaStringCodec(PuaaCodec):
	def __init__(self, fileName, propertyName, formatString):
		PuaaCodec.__init__(self, fileName, [propertyName])
		self.propertyName = propertyName
		self.formatString = formatString

	def compile(self, puaa, f):
		values = {}
		for line in f:
			fields = splitLine(line)
			if fields is None or len(fields) < 2:
				continue
			try:
				fcp, lcp = splitRange(fields[0])
				v = fields[1].strip()
				for cp in range(fcp, lcp+1):
					values[cp] = v
			except:
				pass
		puaa.subtable(self.propertyName, True).entries += entriesFromStringMap(values)

	def decompile(self, puaa, f):
		values = puaa.subtable(self.propertyName, False)
		if values is None or not values.entries:
			return
		for run in runsFromEntries(values.entries):
			print(self.formatString % (joinRange(run), run.value), file=f)

class PuaaUnihanCodec(PuaaCodec):
	def __init__(self, fileName, propertyNames):
		PuaaCodec.__init__(self, fileName, propertyNames)

	def compile(self, puaa, f):
		props = {}
		for line in f:
			line = line.strip()
			if len(line) == 0 or line[0] == '#' or line[0] == b'#' or line[0] == u'#':
				continue
			fields = re.split('\\s+', line, 2)
			if len(fields) < 3:
				continue
			try:
				cp = int(re.sub('^([Uu][+]|[0][Xx])', '', fields[0]), 16)
				if fields[1] not in props:
					props[fields[1]] = {}
				props[fields[1]][cp] = fields[2]
			except:
				pass
		for prop, m in props.items():
			entries = entriesFromDecimalStringMap(m)
			if entries is None:
				entries = entriesFromHexadecimalStringMap(m)
				if entries is None:
					entries = entriesFromNameMap(m)
			puaa.subtable(prop, True).entries += entries

	def decompile(self, puaa, f):
		props = {}
		for prop in self.propertyNames:
			st = puaa.subtable(prop, False)
			if st is None or not st.entries:
				continue
			for cp, value in mapFromEntries(st.entries).items():
				if cp not in props:
					props[cp] = {}
				props[cp][prop] = value
		for cp, m in sortedMap(props):
			for prop in self.propertyNames:
				if prop in m and m[prop]:
					print(u'U+%04X\t%s\t%s' % (cp, prop, m[prop]), file=f)


class ArabicShapingCodec(PuaaCodec):
	def __init__(self):
		PuaaCodec.__init__(self, 'ArabicShaping.txt', [
			'Joining_Type', 'Joining_Group'
		])

	def compile(self, puaa, f):
		types = {}
		groups = {}
		for line in f:
			fields = splitLine(line)
			if fields is None or len(fields) < 4:
				continue
			try:
				fcp, lcp = splitRange(fields[0])
				t = fields[2].strip()
				g = fields[3].strip()
				for cp in range(fcp, lcp+1):
					types[cp] = t
					groups[cp] = g
			except:
				pass
		puaa.subtable('Joining_Type', True).entries += entriesFromStringMap(types)
		puaa.subtable('Joining_Group', True).entries += entriesFromNameMap(groups)

	def decompile(self, puaa, f):
		lines = {}
		names = puaa.subtable('Name', False)
		def getName(cp):
			if names is not None and names.entries:
				name = names.propertyValue(cp)
				if name is not None and len(name) != 0:
					return name
			return ''
		types = puaa.subtable('Joining_Type', False)
		if types is not None and types.entries:
			for entry in types.entries:
				for cp in range(entry.firstCodePoint, entry.lastCodePoint+1):
					value = entry.propertyValue(cp)
					if value is None or len(value) == 0:
						continue
					if cp not in lines:
						lines[cp] = ['%04X' % cp, getName(cp), value, None]
					elif lines[cp][2] is None:
						lines[cp][2] = value
					else:
						lines[cp][2] += value
		groups = puaa.subtable('Joining_Group', False)
		if groups is not None and groups.entries:
			for entry in groups.entries:
				for cp in range(entry.firstCodePoint, entry.lastCodePoint+1):
					value = entry.propertyValue(cp)
					if value is None or len(value) == 0:
						continue
					if cp not in lines:
						lines[cp] = ['%04X' % cp, getName(cp), None, value]
					elif lines[cp][3] is None:
						lines[cp][3] = value
					else:
						lines[cp][3] += value
		for cp, line in sortedMap(lines):
			print(u'; '.join(line), file=f)

class BidiBracketsCodec(PuaaCodec):
	def __init__(self):
		PuaaCodec.__init__(self, 'BidiBrackets.txt', [
			'Bidi_Paired_Bracket', 'Bidi_Paired_Bracket_Type'
		])

	def compile(self, puaa, f):
		values = {}
		types = {}
		for line in f:
			fields = splitLine(line)
			if fields is None or len(fields) < 3:
				continue
			try:
				fcp, lcp = splitRange(fields[0])
				v = int(fields[1].strip(), 16)
				t = fields[2].strip()
				for cp in range(fcp, lcp+1):
					values[cp] = v
					types[cp] = t
			except:
				pass
		puaa.subtable('Bidi_Paired_Bracket', True).entries += entriesFromHexadecimalMap(values)
		puaa.subtable('Bidi_Paired_Bracket_Type', True).entries += entriesFromStringMap(types)

	def decompile(self, puaa, f):
		lines = {}
		values = puaa.subtable('Bidi_Paired_Bracket', False)
		if values is not None and values.entries:
			for entry in values.entries:
				for cp in range(entry.firstCodePoint, entry.lastCodePoint+1):
					value = entry.propertyValue(cp)
					if value is None or len(value) == 0:
						continue
					if cp not in lines:
						lines[cp] = ['%04X' % cp, value, None]
					else:
						lines[cp][1] = value
		types = puaa.subtable('Bidi_Paired_Bracket_Type', False)
		if types is not None and types.entries:
			for entry in types.entries:
				for cp in range(entry.firstCodePoint, entry.lastCodePoint+1):
					value = entry.propertyValue(cp)
					if value is None or len(value) == 0:
						continue
					if cp not in lines:
						lines[cp] = ['%04X' % cp, None, value]
					else:
						lines[cp][2] = value
		for cp, line in sortedMap(lines):
			print(u'; '.join(line), file=f)

class BidiMirroringCodec(PuaaCodec):
	def __init__(self):
		PuaaCodec.__init__(self, 'BidiMirroring.txt', ['Bidi_Mirroring_Glyph'])

	def compile(self, puaa, f):
		values = {}
		for line in f:
			fields = splitLine(line)
			if fields is None or len(fields) < 2:
				continue
			try:
				fcp, lcp = splitRange(fields[0])
				v = int(fields[1].strip(), 16)
				for cp in range(fcp, lcp+1):
					values[cp] = v
			except:
				pass
		puaa.subtable('Bidi_Mirroring_Glyph', True).entries += entriesFromHexadecimalMap(values)

	def decompile(self, puaa, f):
		values = puaa.subtable('Bidi_Mirroring_Glyph', False)
		if values is None or not values.entries:
			return
		for entry in sortedMap(mapFromEntries(values.entries)):
			print(u'%04X; %s' % entry, file=f)

class BlocksCodec(PuaaCodec):
	def __init__(self):
		PuaaCodec.__init__(self, 'Blocks.txt', ['Block'])

	def compile(self, puaa, f):
		blocks = puaa.subtable('Block', True)
		for line in f:
			fields = splitLine(line)
			if fields is None or len(fields) < 2:
				continue
			try:
				fcp, lcp = splitRange(fields[0])
				v = fields[1].strip()
				blocks.entries.append(SingleEntry(fcp, lcp, v))
			except:
				pass

	def decompile(self, puaa, f):
		blocks = puaa.subtable('Block', False)
		if blocks is None or not blocks.entries:
			return
		for entry in blocks.entries:
			print(u'%s; %s' % (joinRange(entry), entry.propertyValue(entry.firstCodePoint)), file=f)

class CompositionExclusionsCodec(PuaaCodec):
	def __init__(self):
		PuaaCodec.__init__(self, 'CompositionExclusions.txt', ['Composition_Exclusion'])

	def compile(self, puaa, f):
		values = {}
		for line in f:
			fields = splitLine(line)
			if fields is None or len(fields) < 1:
				continue
			try:
				fcp, lcp = splitRange(fields[0])
				for cp in range(fcp, lcp+1):
					values[cp] = True
			except:
				pass
		puaa.subtable('Composition_Exclusion', True).entries += entriesFromBooleanMap(values)

	def decompile(self, puaa, f):
		values = puaa.subtable('Composition_Exclusion', False)
		if values is None or not values.entries:
			return
		for cp, value in sortedMap(mapFromEntries(values.entries)):
			if value == 'Y':
				print(u'%04X' % cp, file=f)

class DerivedAgeCodec(PuaaCodec):
	def __init__(self):
		PuaaCodec.__init__(self, 'DerivedAge.txt', ['Age'])

	def compile(self, puaa, f):
		values = {}
		for line in f:
			fields = splitLine(line)
			if fields is None or len(fields) < 2:
				continue
			try:
				fcp, lcp = splitRange(fields[0])
				v = fields[1].strip()
				for cp in range(fcp, lcp+1):
					values[cp] = v
			except:
				pass
		puaa.subtable('Age', True).entries += entriesFromStringMap(values)

	def decompile(self, puaa, f):
		values = puaa.subtable('Age', False)
		if values is None or not values.entries:
			return
		runs = runsFromEntries(values.entries)
		runs.sort(key=lambda e: (naturalSortKey(e.value), e.firstCodePoint, e.lastCodePoint))
		for run in runs:
			print(u'%-14s; %s' % (joinRange(run), run.value), file=f)

class EastAsianWidthCodec(PuaaStringCodec):
	def __init__(self):
		PuaaStringCodec.__init__(self, 'EastAsianWidth.txt', 'East_Asian_Width', u'%s;%s')

class EmojiDataCodec(PuaaPropListCodec):
	def __init__(self):
		PuaaPropListCodec.__init__(self, 'emoji-data.txt', [
			'Emoji', 'Emoji_Presentation',
			'Emoji_Modifier', 'Emoji_Modifier_Base',
			'Emoji_Component', 'Extended_Pictographic'
		])

class EquivalentUnifiedIdeographCodec(PuaaCodec):
	def __init__(self):
		PuaaCodec.__init__(self, 'EquivalentUnifiedIdeograph.txt', ['Equivalent_Unified_Ideograph'])

	def compile(self, puaa, f):
		values = {}
		for line in f:
			fields = splitLine(line)
			if fields is None or len(fields) < 2:
				continue
			try:
				fcp, lcp = splitRange(fields[0])
				v = int(fields[1].strip(), 16)
				for cp in range(fcp, lcp+1):
					values[cp] = v
			except:
				pass
		puaa.subtable('Equivalent_Unified_Ideograph', True).entries += entriesFromHexadecimalMap(values)

	def decompile(self, puaa, f):
		values = puaa.subtable('Equivalent_Unified_Ideograph', False)
		if values is None or not values.entries:
			return
		for run in runsFromEntries(values.entries):
			print(u'%-11s; %s' % (joinRange(run), run.value), file=f)

class GraphemeBreakPropertyCodec(PuaaCategoryCodec):
	def __init__(self):
		PuaaCategoryCodec.__init__(self, 'GraphemeBreakProperty.txt', 'Grapheme_Cluster_Break', [
			'Prepend', 'CR', 'LF', 'Control', 'Extend',
			'Regional_Indicator', 'SpacingMark',
			'L', 'V', 'T', 'LV', 'LVT', 'ZWJ'
		])

class HangulSyllableTypeCodec(PuaaCodec):
	def __init__(self):
		PuaaCodec.__init__(self, 'HangulSyllableType.txt', ['Hangul_Syllable_Type'])

	def compile(self, puaa, f):
		values = {}
		for line in f:
			fields = splitLine(line)
			if fields is None or len(fields) < 2:
				continue
			try:
				fcp, lcp = splitRange(fields[0])
				v = fields[1].strip()
				for cp in range(fcp, lcp+1):
					values[cp] = v
			except:
				pass
		puaa.subtable('Hangul_Syllable_Type', True).entries += entriesFromStringMap(values)

	def decompile(self, puaa, f):
		values = puaa.subtable('Hangul_Syllable_Type', False)
		if values is None or not values.entries:
			return
		runs = runsFromEntries(values.entries)
		firstOfType = {}
		for run in runs:
			if run.value in firstOfType:
				if firstOfType[run.value] < run.firstCodePoint:
					continue
			firstOfType[run.value] = run.firstCodePoint
		runs.sort(key=lambda e: (firstOfType[e.value], e.value, e.firstCodePoint, e.lastCodePoint))
		for run in runs:
			print(u'%-14s; %s' % (joinRange(run), run.value), file=f)

class IndicPositionalPuaaCategoryCodec(PuaaCategoryCodec):
	def __init__(self):
		PuaaCategoryCodec.__init__(self, 'IndicPositionalCategory.txt', 'Indic_Positional_Category', [
			'Right', 'Left', 'Visual_Order_Left', 'Left_And_Right',
			'Top', 'Bottom', 'Top_And_Bottom', 'Top_And_Right', 'Top_And_Left',
			'Top_And_Left_And_Right', 'Bottom_And_Right', 'Bottom_And_Left',
			'Top_And_Bottom_And_Right', 'Top_And_Bottom_And_Left', 'Overstruck'
		])

class IndicSyllabicPuaaCategoryCodec(PuaaCategoryCodec):
	def __init__(self):
		PuaaCategoryCodec.__init__(self, 'IndicSyllabicCategory.txt', 'Indic_Syllabic_Category', [
			'Bindu', 'Visarga', 'Avagraha', 'Nukta', 'Virama', 'Pure_Killer',
			'Invisible_Stacker', 'Vowel_Independent', 'Vowel_Dependent',
			'Vowel', 'Consonant_Placeholder', 'Consonant', 'Consonant_Dead',
			'Consonant_With_Stacker', 'Consonant_Prefixed',
			'Consonant_Preceding_Repha', 'Consonant_Initial_Postfixed',
			'Consonant_Succeeding_Repha', 'Consonant_Subjoined',
			'Consonant_Medial', 'Consonant_Final', 'Consonant_Head_Letter',
			'Modifying_Letter', 'Tone_Letter', 'Tone_Mark', 'Gemination_Mark',
			'Cantillation_Mark', 'Register_Shifter', 'Syllable_Modifier',
			'Consonant_Killer', 'Non_Joiner', 'Joiner', 'Number_Joiner',
			'Number', 'Brahmi_Joining_Number'
		])

class JamoCodec(PuaaCodec):
	def __init__(self):
		PuaaCodec.__init__(self, 'Jamo.txt', ['Jamo_Short_Name'])

	def compile(self, puaa, f):
		jamo = puaa.subtable('Jamo_Short_Name', True)
		for line in f:
			fields = splitLine(line)
			if fields is None or len(fields) < 1:
				continue
			try:
				fcp, lcp = splitRange(fields[0])
				v = fields[1].strip() if len(fields) > 1 else '' # U+110B actually is ''
				jamo.entries.append(SingleEntry(fcp, lcp, v))
			except:
				pass

	def decompile(self, puaa, f):
		jamo = puaa.subtable('Jamo_Short_Name', False)
		if jamo is None or not jamo.entries:
			return
		for entry in jamo.entries:
			for cp in range(entry.firstCodePoint, entry.lastCodePoint+1):
				print(u'%04X; %s' % (cp, entry.propertyValue(cp)), file=f)

class LineBreakCodec(PuaaStringCodec):
	def __init__(self):
		PuaaStringCodec.__init__(self, 'LineBreak.txt', 'Line_Break', u'%s;%s')

class NameAliasesCodec(PuaaCodec):
	def __init__(self):
		PuaaCodec.__init__(self, 'NameAliases.txt', ['Name_Alias'])

	def compile(self, puaa, f):
		names = puaa.subtable('Name_Alias', True)
		for line in f:
			fields = splitLine(line)
			if fields is None or len(fields) < 3:
				continue
			try:
				fcp, lcp = splitRange(fields[0])
				n = fields[1].strip()
				t = fields[2].strip()
				names.entries.append(NameAliasEntry(fcp, lcp, n, t))
			except:
				pass

	def decompile(self, puaa, f):
		names = puaa.subtable('Name_Alias', False)
		if names is None or not names.entries:
			return
		for entry in names.entries:
			for cp in range(entry.firstCodePoint, entry.lastCodePoint+1):
				print(u'%04X;%s' % (cp, entry.propertyValue(cp)), file=f)

class NushuSourcesCodec(PuaaUnihanCodec):
	def __init__(self):
		PuaaUnihanCodec.__init__(self, 'NushuSources.txt', [
			'kSrc_NushuDuben', 'kReading'
		])

class PropListCodec(PuaaPropListCodec):
	def __init__(self):
		PuaaPropListCodec.__init__(self, 'PropList.txt', [
			'White_Space', 'Bidi_Control', 'Join_Control', 'Dash',
			'Hyphen', 'Quotation_Mark', 'Terminal_Punctuation',
			'Other_Math', 'Hex_Digit', 'ASCII_Hex_Digit',
			'Other_Alphabetic', 'Ideographic', 'Diacritic',
			'Extender', 'Other_Lowercase', 'Other_Uppercase',
			'Noncharacter_Code_Point', 'Other_Grapheme_Extend',
			'IDS_Binary_Operator', 'IDS_Trinary_Operator',
			'IDS_Unary_Operator', 'Radical', 'Unified_Ideograph',
			'Other_Default_Ignorable_Code_Point', 'Deprecated',
			'Soft_Dotted', 'Logical_Order_Exception',
			'Other_ID_Start', 'Other_ID_Continue',
			'ID_Compat_Math_Continue', 'ID_Compat_Math_Start',
			'Sentence_Terminal', 'Variation_Selector',
			'Pattern_White_Space', 'Pattern_Syntax',
			'Prepended_Concatenation_Mark', 'Regional_Indicator'
		])

class ScriptExtensionsCodec(PuaaCodec):
	def __init__(self):
		PuaaCodec.__init__(self, 'ScriptExtensions.txt', ['Script_Extensions'])

	def compile(self, puaa, f):
		values = {}
		for line in f:
			fields = splitLine(line)
			if fields is None or len(fields) < 2:
				continue
			try:
				fcp, lcp = splitRange(fields[0])
				for s in re.split('\\s+', fields[1].strip()):
					if not s in values:
						values[s] = {}
					for cp in range(fcp, lcp+1):
						values[s][cp] = s
			except:
				pass
		st = puaa.subtable('Script_Extensions', True)
		for s, m in sortedMap(values):
			st.entries += entriesFromStringMap(m)

	def decompile(self, puaa, f):
		st = puaa.subtable('Script_Extensions', False)
		if st is None or not st.entries:
			return
		scripts = {}
		for entry in st.entries:
			for cp in range(entry.firstCodePoint, entry.lastCodePoint+1):
				if not cp in scripts:
					scripts[cp] = []
				scripts[cp] += re.split('\\s+', entry.propertyValue(cp).strip())
		runs = runsFromEntries([SingleEntry(cp, cp, ' '.join(sorted(s))) for cp, s in scripts.items()])
		runs.sort(key=lambda e: (len(e.value), e.value.lower(), e.firstCodePoint, e.lastCodePoint))
		for run in runs:
			print(u'%-14s; %s' % (joinRange(run), run.value), file=f)

class ScriptsCodec(PuaaCodec):
	def __init__(self):
		PuaaCodec.__init__(self, 'Scripts.txt', ['Script'])

	def compile(self, puaa, f):
		values = {}
		for line in f:
			fields = splitLine(line)
			if fields is None or len(fields) < 2:
				continue
			try:
				fcp, lcp = splitRange(fields[0])
				v = fields[1].strip()
				for cp in range(fcp, lcp+1):
					values[cp] = v
			except:
				pass
		puaa.subtable('Script', True).entries += entriesFromStringMap(values)

	def decompile(self, puaa, f):
		values = puaa.subtable('Script', False)
		if values is None or not values.entries:
			return
		runs = runsFromEntries(values.entries)
		firstOfScript = {}
		for run in runs:
			if run.value in firstOfScript:
				if firstOfScript[run.value] < run.firstCodePoint:
					continue
			firstOfScript[run.value] = run.firstCodePoint
		runs.sort(key=lambda e: (firstOfScript[e.value], e.value, e.firstCodePoint, e.lastCodePoint))
		for run in runs:
			print(u'%-14s; %s' % (joinRange(run), run.value), file=f)

class SentenceBreakPropertyCodec(PuaaCategoryCodec):
	def __init__(self):
		PuaaCategoryCodec.__init__(self, 'SentenceBreakProperty.txt', 'Sentence_Break', [
			'CR', 'LF', 'Extend', 'Sep', 'Format', 'Sp',
			'Lower', 'Upper', 'OLetter', 'Numeric',
			'ATerm', 'STerm', 'Close', 'SContinue'
		])

class SpecialCasingCodec(PuaaCodec):
	def __init__(self):
		PuaaCodec.__init__(self, 'SpecialCasing.txt', [
			'Lowercase_Mapping', 'Titlecase_Mapping', 'Uppercase_Mapping'
		])

	def compile(self, puaa, f):
		lower = puaa.subtable('Lowercase_Mapping', True)
		title = puaa.subtable('Titlecase_Mapping', True)
		upper = puaa.subtable('Uppercase_Mapping', True)
		for line in f:
			fields = splitLine(line)
			if fields is None or len(fields) < 4:
				continue
			try:
				fcp, lcp = splitRange(fields[0])
				condition = fields[4].strip() if len(fields) > 4 and fields[4].strip() else None
			except:
				continue
			try:
				lc = [int(word, 16) for word in re.split('\\s+', fields[1].strip())]
				if lc:
					lower.entries.append(CaseMappingEntry(fcp, lcp, lc, condition))
			except:
				pass
			try:
				tc = [int(word, 16) for word in re.split('\\s+', fields[2].strip())]
				if tc:
					title.entries.append(CaseMappingEntry(fcp, lcp, tc, condition))
			except:
				pass
			try:
				uc = [int(word, 16) for word in re.split('\\s+', fields[3].strip())]
				if uc:
					upper.entries.append(CaseMappingEntry(fcp, lcp, uc, condition))
			except:
				pass

	def decompile(self, puaa, f):
		keys = []
		lines = {}
		def addLines(prop, i):
			st = puaa.subtable(prop, False)
			if st is None or not st.entries:
				return
			for entry in st.entries:
				for cp in range(entry.firstCodePoint, entry.lastCodePoint+1):
					key = '%08X' % (0xC0000000 + cp)
					value = entry.propertyValue(cp)
					condition = None
					if ';' in value:
						v, c = value.split(';', 1)
						value = v.strip()
						condition = c.strip()
						key += condition
					if key not in lines:
						keys.append(key)
						lines[key] = ['%04X' % cp, None, None, None, condition]
					lines[key][i] = value
		addLines('Lowercase_Mapping', 1)
		addLines('Titlecase_Mapping', 2)
		addLines('Uppercase_Mapping', 3)
		for key in keys:
			line = lines[key]
			if line[4] is None:
				print(u'%s; %s; %s; %s;' % tuple(u'' if field is None else field for field in line[0:4]), file=f)
			else:
				print(u'%s; %s; %s; %s; %s;' % tuple(u'' if field is None else field for field in line), file=f)

class TangutSourcesCodec(PuaaUnihanCodec):
	def __init__(self):
		PuaaUnihanCodec.__init__(self, 'TangutSources.txt', [
			'kTGT_MergedSrc', 'kRSTUnicode'
		])

class UnicodeDataCodec(PuaaCodec):
	def __init__(self):
		PuaaCodec.__init__(self, 'UnicodeData.txt', [
			'Name', 'General_Category', 'Canonical_Combining_Class',
			'Bidi_Class', 'Decomposition_Type', 'Decomposition_Mapping',
			'Numeric_Type', 'Numeric_Value', 'Bidi_Mirrored',
			'Unicode_1_Name', 'ISO_Comment', 'Simple_Uppercase_Mapping',
			'Simple_Lowercase_Mapping', 'Simple_Titlecase_Mapping'
		])

	def compile(self, puaa, f):
		names = {}
		categories = {}
		combClasses = {}
		bidiClasses = {}
		decompTypes = {}
		decompMappings = {}
		numericTypes = {}
		numericValues = {}
		bidiMirrored = {}
		uni1Names = {}
		comments = {}
		uppercase = {}
		lowercase = {}
		titlecase = {}
		for line in f:
			fields = splitLine(line)
			if fields is None or len(fields) < 12:
				continue
			try:
				cp = int(fields[0], 16)
			except:
				continue
			if fields[1].strip():
				names[cp] = fields[1].strip()
			if fields[2].strip():
				categories[cp] = fields[2].strip()
			try:
				combClasses[cp] = int(fields[3].strip())
			except:
				pass
			if fields[4].strip():
				bidiClasses[cp] = fields[4].strip()
			if fields[5].strip():
				types = []
				mappings = []
				for word in re.split('\\s+', fields[5].strip()):
					try:
						mappings.append(int(word, 16))
					except:
						types.append(word)
				if types:
					decompTypes[cp] = ' '.join(types)
				if mappings:
					decompMappings[cp] = mappings
			if fields[6].strip():
				numericTypes[cp] = 'Decimal'
				numericValues[cp] = fields[6].strip()
			elif fields[7].strip():
				numericTypes[cp] = 'Digit'
				numericValues[cp] = fields[7].strip()
			elif fields[8].strip():
				numericTypes[cp] = 'Numeric'
				numericValues[cp] = fields[8].strip()
			if fields[9].strip():
				bidiMirrored[cp] = (fields[9].strip() == 'Y')
			if fields[10].strip():
				uni1Names[cp] = fields[10].strip()
			if fields[11].strip():
				comments[cp] = fields[11].strip()
			try:
				uppercase[cp] = int(fields[12].strip(), 16)
			except:
				pass
			try:
				lowercase[cp] = int(fields[13].strip(), 16)
			except:
				pass
			try:
				titlecase[cp] = int(fields[14].strip(), 16)
			except:
				pass
		puaa.subtable('Name', True).entries += entriesFromNameMap(names)
		puaa.subtable('General_Category', True).entries += entriesFromStringMap(categories)
		puaa.subtable('Canonical_Combining_Class', True).entries += entriesFromDecimalMap(combClasses)
		puaa.subtable('Bidi_Class', True).entries += entriesFromStringMap(bidiClasses)
		puaa.subtable('Decomposition_Type', True).entries += entriesFromStringMap(decompTypes)
		puaa.subtable('Decomposition_Mapping', True).entries += entriesFromHexSequenceMap(decompMappings)
		puaa.subtable('Numeric_Type', True).entries += entriesFromStringMap(numericTypes)
		puaa.subtable('Numeric_Value', True).entries += entriesFromStringMap(numericValues)
		puaa.subtable('Bidi_Mirrored', True).entries += entriesFromBooleanMap(bidiMirrored)
		puaa.subtable('Unicode_1_Name', True).entries += entriesFromNameMap(uni1Names)
		puaa.subtable('ISO_Comment', True).entries += entriesFromStringMap(comments)
		puaa.subtable('Simple_Uppercase_Mapping', True).entries += entriesFromHexadecimalMap(uppercase)
		puaa.subtable('Simple_Lowercase_Mapping', True).entries += entriesFromHexadecimalMap(lowercase)
		puaa.subtable('Simple_Titlecase_Mapping', True).entries += entriesFromHexadecimalMap(titlecase)

	def decompile(self, puaa, f):
		lines = {}
		def addLines(prop, i):
			st = puaa.subtable(prop, False)
			if st is None or not st.entries:
				return
			for entry in st.entries:
				for cp in range(entry.firstCodePoint, entry.lastCodePoint+1):
					value = entry.propertyValue(cp)
					if value is None or len(value) == 0:
						continue
					if cp not in lines:
						lines[cp] = ['%04X' % cp] + [None] * 14
					if lines[cp][i] is None:
						lines[cp][i] = value
					elif i == 8:
						if lines[cp][i] == 'Decimal':
							lines[cp][6] = lines[cp][7] = lines[cp][8] = value
						if lines[cp][i] == 'Digit':
							lines[cp][7] = lines[cp][8] = value
						if lines[cp][i] == 'Numeric':
							lines[cp][8] = value
					else:
						if i == 5:
							lines[cp][i] += ' '
						lines[cp][i] += value
		addLines('Name', 1)
		addLines('General_Category', 2)
		addLines('Canonical_Combining_Class', 3)
		addLines('Bidi_Class', 4)
		addLines('Decomposition_Type', 5)
		addLines('Decomposition_Mapping', 5)
		addLines('Numeric_Type', 8)
		addLines('Numeric_Value', 8)
		addLines('Bidi_Mirrored', 9)
		addLines('Unicode_1_Name', 10)
		addLines('ISO_Comment', 11)
		addLines('Simple_Uppercase_Mapping', 12)
		addLines('Simple_Lowercase_Mapping', 13)
		addLines('Simple_Titlecase_Mapping', 14)
		for cp, line in sortedMap(lines):
			print(u';'.join(u'' if field is None else field for field in line), file=f)

class UnihanDictionaryIndicesCodec(PuaaUnihanCodec):
	def __init__(self):
		PuaaUnihanCodec.__init__(self, 'Unihan_DictionaryIndices.txt', [
			'kCheungBauerIndex', # added in Unicode 5.0
			'kCihaiT',           # moved in Unicode 15.0 (from DictionaryLikeData)
			'kCowles',           #
			'kDaeJaweon',        #
			'kFennIndex',        #
			'kGSR',              #
			'kHanYu',            #
			'kIRGDaeJaweon',     #
			'kIRGDaiKanwaZiten', # removed in Unicode 15.1
			'kIRGHanyuDaZidian', #
			'kIRGKangXi',        #
			'kKangXi',           #
			'kKarlgren',         #
			'kLau',              #
			'kMatthews',         #
			'kMeyerWempe',       #
			'kMorohashi',        #
			'kNelson',           #
			'kSBGY',             #
			'kSMSZD2003Index',   # added in Unicode 15.1
		])

class UnihanDictionaryLikeDataCodec(PuaaUnihanCodec):
	def __init__(self):
		PuaaUnihanCodec.__init__(self, 'Unihan_DictionaryLikeData.txt', [
			'kAlternateTotalStrokes', # added in Unicode 15.0
			'kCangjie',               #
			'kCheungBauer',           # added in Unicode 5.0
			'kFenn',                  #
			'kFourCornerCode',        # added in Unicode 5.0
			'kFrequency',             #
			'kGradeLevel',            #
			'kHDZRadBreak',           #
			'kHKGlyph',               #
			'kMojiJoho',              # added in Unicode 15.1
			'kPhonetic',              #
			'kStrange',               # added in Unicode 14.0
			'kUnihanCore2020',        # added in Unicode 13.0
		])

class UnihanIRGSourcesCodec(PuaaUnihanCodec):
	def __init__(self):
		PuaaUnihanCodec.__init__(self, 'Unihan_IRGSources.txt', [
			'kCompatibilityVariant', #
			'kIICore',               #
			'kIRG_GSource',          #
			'kIRG_HSource',          #
			'kIRG_JSource',          #
			'kIRG_KPSource',         #
			'kIRG_KSource',          #
			'kIRG_MSource',          # added in Unicode 5.2
			'kIRG_SSource',          # added in Unicode 13.0
			'kIRG_TSource',          #
			'kIRG_UKSource',         # added in Unicode 13.0
			'kIRG_USource',          #
			'kIRG_VSource',          #
			'kRSUnicode',            #
			'kTotalStrokes',         #
		])

class UnihanNumericValuesCodec(PuaaUnihanCodec):
	def __init__(self):
		PuaaUnihanCodec.__init__(self, 'Unihan_NumericValues.txt', [
			'kAccountingNumeric', #
			'kOtherNumeric',      #
			'kPrimaryNumeric',    #
			'kVietnameseNumeric', # added in Unicode 15.1
			'kZhuangNumeric',     # added in Unicode 15.1
		])

class UnihanOtherMappingsCodec(PuaaUnihanCodec):
	def __init__(self):
		PuaaUnihanCodec.__init__(self, 'Unihan_OtherMappings.txt', [
			'kBigFive',              #
			'kCCCII',                #
			'kCNS1986',              #
			'kCNS1992',              #
			'kEACC',                 #
			'kGB0',                  #
			'kGB1',                  #
			'kGB3',                  #
			'kGB5',                  #
			'kGB7',                  #
			'kGB8',                  #
			'kHKSCS',                # removed in Unicode 15.1
			'kIBMJapan',             #
			'kJa',                   # added in Unicode 8.0
			'kJinmeiyoKanji',        # added in Unicode 11.0
			'kJis0',                 #
			'kJis1',                 #
			'kJIS0213',              #
			'kJoyoKanji',            # added in Unicode 11.0
			'kKPS0',                 # removed in Unicode 15.1
			'kKPS1',                 # removed in Unicode 15.1
			'kKSC0',                 # removed in Unicode 15.1
			'kKSC1',                 # removed in Unicode 15.1
			'kKoreanEducationHanja', # added in Unicode 11.0
			'kKoreanName',           # added in Unicode 11.0
			'kMainlandTelegraph',    #
			'kPseudoGB1',            #
			'kTaiwanTelegraph',      #
			'kTGH',                  # added in Unicode 11.0
			'kXerox',                #
		])

class UnihanRadicalStrokeCountsCodec(PuaaUnihanCodec):
	def __init__(self):
		PuaaUnihanCodec.__init__(self, 'Unihan_RadicalStrokeCounts.txt', [
			'kRSAdobe_Japan1_6', #
			'kRSJapanese',       # removed in Unicode 13.0
			'kRSKangXi',         # removed in Unicode 15.1
			'kRSKanWa',          # removed in Unicode 13.0
			'kRSKorean',         # removed in Unicode 13.0
		])

class UnihanReadingsCodec(PuaaUnihanCodec):
	def __init__(self):
		PuaaUnihanCodec.__init__(self, 'Unihan_Readings.txt', [
			'kCantonese',         #
			'kDefinition',        #
			'kHangul',            # added in Unicode 5.0
			'kHanyuPinlu',        #
			'kHanyuPinyin',       # added in Unicode 5.2
			'kJapanese',          # added in Unicode 15.1
			'kJapaneseKun',       #
			'kJapaneseOn',        #
			'kKorean',            #
			'kMandarin',          #
			'kSMSZD2003Readings', # added in Unicode 15.1
			'kTang',              #
			'kTGHZ2013',          # added in Unicode 13.0
			'kVietnamese',        #
			'kXHC1983',           # added in Unicode 5.1
		])

class UnihanVariantsCodec(PuaaUnihanCodec):
	def __init__(self):
		PuaaUnihanCodec.__init__(self, 'Unihan_Variants.txt', [
			'kSemanticVariant',            #
			'kSimplifiedVariant',          #
			'kSpecializedSemanticVariant', #
			'kSpoofingVariant',            # added in Unicode 13.0
			'kTraditionalVariant',         #
			'kZVariant',                   #
		])

class VerticalOrientationCodec(PuaaStringCodec):
	def __init__(self):
		PuaaStringCodec.__init__(self, 'VerticalOrientation.txt', 'Vertical_Orientation', u'%-14s; %s')

class WordBreakPropertyCodec(PuaaCategoryCodec):
	def __init__(self):
		PuaaCategoryCodec.__init__(self, 'WordBreakProperty.txt', 'Word_Break', [
			'Double_Quote', 'Single_Quote', 'Hebrew_Letter',
			'CR', 'LF', 'Newline', 'Extend', 'Regional_Indicator',
			'Format', 'Katakana', 'ALetter', 'MidLetter', 'MidNum',
			'MidNumLet', 'Numeric', 'ExtendNumLet', 'ZWJ', 'WSegSpace'
		])


CODECS = [
	ArabicShapingCodec(),
	BidiBracketsCodec(),
	BidiMirroringCodec(),
	BlocksCodec(),
	CompositionExclusionsCodec(),
	DerivedAgeCodec(),
	EastAsianWidthCodec(),
	EmojiDataCodec(),
	EquivalentUnifiedIdeographCodec(),
	GraphemeBreakPropertyCodec(),
	HangulSyllableTypeCodec(),
	IndicPositionalPuaaCategoryCodec(),
	IndicSyllabicPuaaCategoryCodec(),
	JamoCodec(),
	LineBreakCodec(),
	NameAliasesCodec(),
	NushuSourcesCodec(),
	PropListCodec(),
	ScriptExtensionsCodec(),
	ScriptsCodec(),
	SentenceBreakPropertyCodec(),
	SpecialCasingCodec(),
	TangutSourcesCodec(),
	UnicodeDataCodec(),
	UnihanDictionaryIndicesCodec(),
	UnihanDictionaryLikeDataCodec(),
	UnihanIRGSourcesCodec(),
	UnihanNumericValuesCodec(),
	UnihanOtherMappingsCodec(),
	UnihanRadicalStrokeCountsCodec(),
	UnihanReadingsCodec(),
	UnihanVariantsCodec(),
	VerticalOrientationCodec(),
	WordBreakPropertyCodec(),
]

CODEC_MAP = {c.fileName.lower(): c for c in CODECS}

def getCodec(fileName):
	fileName = fileName.lower()
	return CODEC_MAP[fileName] if fileName in CODEC_MAP else None

def printFileNames():
	fileNames = [c.fileName for c in CODECS]
	longest = max(len(fileName) for fileName in fileNames)
	columns = 80 // (longest + 2)
	if columns < 1:
		columns = 1
		longest = 0
	rows = (len(fileNames) + columns - 1) // columns
	fmt = '  %%-%ds' % longest
	for i in range(0, rows):
		items = []
		for j in range(0, columns):
			k = j * rows + i
			if k < len(fileNames):
				items.append(fmt % fileNames[k])
		print(''.join(items))

def compilePUAA(paths, verbose=False):
	puaa = PuaaTable()
	def compile(path):
		if os.path.isdir(path):
			for f in os.listdir(path):
				if f[0] != '.':
					compile(os.path.join(path, f))
		else:
			codec = getCodec(os.path.basename(path))
			if codec is not None:
				if verbose:
					print('Compiling from %s...' % codec.fileName)
				with io.open(path, mode='r', encoding='utf8') as f:
					codec.compile(puaa, f)
	for path in paths:
		compile(path)
	return puaa

def decompilePUAA(puaa, dst, verbose=False):
	if not os.path.exists(dst):
		os.makedirs(dst)
	for codec in CODECS:
		for propertyName in codec.propertyNames:
			if puaa.subtable(propertyName) is not None:
				if verbose:
					print('Decompiling to %s...' % codec.fileName)
				with io.open(os.path.join(dst, codec.fileName), mode='w', encoding='utf8') as f:
					codec.decompile(puaa, f)
				break


def ifExists(path):
	return path if os.path.exists(path) else None

def compile(args):
	def printHelp():
		print()
		print('pypuaa compile - Add Unicode Character Database properties to TrueType files.')
		print()
		print('  -d <path>     Specify UCD data file or directory.')
		print('  -i <path>     Specify source TrueType file.')
		print('  -o <path>     Specify destination TrueType file.')
		print('  -D            Process arguments as UCD data files.')
		print('  -I            Process arguments as source files.')
		print('  -O            Process arguments as destination files.')
		print('  --            Process remaining arguments as file names.')
		print()
		print('Source and destination may be the same file.')
		print('Other files specified must be in the format of the')
		print('Unicode Character Database and be named accordingly:')
		print()
		printFileNames()
		print()
		print('Files other than those listed above will be ignored.')
		print()
	if not args:
		printHelp()
		return
	dataFiles = []
	inputFiles = []
	outputFiles = []
	defaultList = dataFiles
	parsingOptions = True
	verbose = True
	argi = 0
	while argi < len(args):
		arg = args[argi]
		argi += 1
		if parsingOptions and arg.startswith('-'):
			if arg == '--':
				parsingOptions = False
			elif arg == '-d' and argi < len(args):
				dataFiles.append(args[argi])
				argi += 1
			elif arg == '-i' and argi < len(args):
				inputFiles.append(args[argi])
				argi += 1
			elif arg == '-o' and argi < len(args):
				outputFiles.append(args[argi])
				argi += 1
			elif arg == '-D':
				defaultList = dataFiles
			elif arg == '-I':
				defaultList = inputFiles
			elif arg == '-O':
				defaultList = outputFiles
			elif arg == '-q':
				verbose = False
			elif arg == '-v':
				verbose = True
			elif arg == '--help':
				printHelp()
				return
			else:
				print('Unknown option: %s' % arg)
				return
		else:
			defaultList.append(arg)
	if not dataFiles:
		print('No data files specified.')
		return
	puaa = compilePUAA(dataFiles, verbose=verbose)
	if not inputFiles and not outputFiles:
		writePUAA(ifExists('puaa.out'), puaa, 'puaa.out', verbose=verbose)
		return
	if not inputFiles or not outputFiles:
		for file in inputFiles:
			writePUAA(ifExists(file), puaa, file, verbose=verbose)
		for file in outputFiles:
			writePUAA(ifExists(file), puaa, file, verbose=verbose)
		return
	if len(inputFiles) == 1 and len(outputFiles) == 1:
		writePUAA(inputFiles[0], puaa, outputFiles[0], verbose=verbose)
		return
	if len(inputFiles) > 1:
		print('Too many input files.')
	if len(outputFiles) > 1:
		print('Too many output files.')

def decompile(args):
	def printHelp():
		print()
		print('pypuaa decompile - Create UCD files from character properties in TrueType files.')
		print()
		print('  -i <path>     Specify source TrueType file.')
		print('  -o <path>     Specify destination directory.')
		print('  -I            Process arguments as source files.')
		print('  -O            Process arguments as destination files.')
		print('  --            Process remaining arguments as file names.')
		print()
		print('Output files will be in the format of the Unicode Character Database')
		print('(although without any comments) and will be named accordingly:')
		print()
		printFileNames()
		print()
		print('Only files for properties present in the source files will be generated.')
		print()
	if not args:
		printHelp()
		return
	inputFiles = []
	outputFiles = []
	defaultList = inputFiles
	parsingOptions = True
	verbose = True
	argi = 0
	while argi < len(args):
		arg = args[argi]
		argi += 1
		if parsingOptions and arg.startswith('-'):
			if arg == '--':
				parsingOptions = False
			elif arg == '-i' and argi < len(args):
				inputFiles.append(args[argi])
				argi += 1
			elif arg == '-o' and argi < len(args):
				outputFiles.append(args[argi])
				argi += 1
			elif arg == '-I':
				defaultList = inputFiles
			elif arg == '-O':
				defaultList = outputFiles
			elif arg == '-q':
				verbose = False
			elif arg == '-v':
				verbose = True
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
		return
	if not outputFiles:
		outputFiles.append('puaa.d')
	if len(inputFiles) == 1:
		puaa = readPUAA(inputFiles[0], verbose=verbose)
		if puaa is not None:
			for outputFile in outputFiles:
				decompilePUAA(puaa, outputFile, verbose=verbose)
		return
	if len(outputFiles) == 1:
		for inputFile in inputFiles:
			puaa = readPUAA(inputFile, verbose=verbose)
			if puaa is not None:
				decompilePUAA(puaa, outputFiles[0], verbose=verbose)
		return
	if len(inputFiles) > 1:
		print('Too many input files.')
	if len(outputFiles) > 1:
		print('Too many output files.')

def copy(args):
	def printHelp():
		print()
		print('pypuaa copy - Copy Unicode Character Database properties across TrueType files.')
		print()
		print('  -d <path>     Specify source file for character properties.')
		print('  -i <path>     Specify source file for font tables.')
		print('  -o <path>     Specify destination TrueType file.')
		print('  -D            Process arguments as source files for character properties.')
		print('  -I            Process arguments as source files for font tables.')
		print('  -O            Process arguments as destination files.')
		print('  --            Process remaining arguments as file names.')
		print()
		print('Source and destination may be the same file.')
		print()
	if not args:
		printHelp()
		return
	dataFiles = []
	inputFiles = []
	outputFiles = []
	defaultList = dataFiles
	parsingOptions = True
	verbose = True
	argi = 0
	while argi < len(args):
		arg = args[argi]
		argi += 1
		if parsingOptions and arg.startswith('-'):
			if arg == '--':
				parsingOptions = False
			elif arg == '-d' and argi < len(args):
				dataFiles.append(args[argi])
				argi += 1
			elif arg == '-i' and argi < len(args):
				inputFiles.append(args[argi])
				argi += 1
			elif arg == '-o' and argi < len(args):
				outputFiles.append(args[argi])
				argi += 1
			elif arg == '-D':
				defaultList = dataFiles
			elif arg == '-I':
				defaultList = inputFiles
			elif arg == '-O':
				defaultList = outputFiles
			elif arg == '-q':
				verbose = False
			elif arg == '-v':
				verbose = True
			elif arg == '--help':
				printHelp()
				return
			else:
				print('Unknown option: %s' % arg)
				return
		else:
			defaultList.append(arg)
	if not dataFiles:
		print('No data files specified.')
		return
	if len(dataFiles) > 1:
		print('Too many data files.')
		return
	puaa = readPUAA(dataFiles[0], verbose=verbose)
	if not inputFiles and not outputFiles:
		writePUAA(ifExists('puaa.out'), puaa, 'puaa.out', verbose=verbose)
		return
	if not inputFiles or not outputFiles:
		for file in inputFiles:
			writePUAA(ifExists(file), puaa, file, verbose=verbose)
		for file in outputFiles:
			writePUAA(ifExists(file), puaa, file, verbose=verbose)
		return
	if len(inputFiles) == 1 and len(outputFiles) == 1:
		writePUAA(inputFiles[0], puaa, outputFiles[0], verbose=verbose)
		return
	if len(inputFiles) > 1:
		print('Too many input files.')
	if len(outputFiles) > 1:
		print('Too many output files.')

def strip(args):
	def printHelp():
		print()
		print('pypuaa strip - Remove Unicode Character Database properties from TrueType files.')
		print()
		print('  -i <path>     Specify source TrueType file.')
		print('  -o <path>     Specify destination TrueType file.')
		print('  -I            Process arguments as source files.')
		print('  -O            Process arguments as destination files.')
		print('  --            Process remaining arguments as file names.')
		print()
		print('Source and destination may be the same file.')
		print()
	if not args:
		printHelp()
		return
	inputFiles = []
	outputFiles = []
	defaultList = inputFiles
	parsingOptions = True
	verbose = True
	argi = 0
	while argi < len(args):
		arg = args[argi]
		argi += 1
		if parsingOptions and arg.startswith('-'):
			if arg == '--':
				parsingOptions = False
			elif arg == '-i' and argi < len(args):
				inputFiles.append(args[argi])
				argi += 1
			elif arg == '-o' and argi < len(args):
				outputFiles.append(args[argi])
				argi += 1
			elif arg == '-I':
				defaultList = inputFiles
			elif arg == '-O':
				defaultList = outputFiles
			elif arg == '-q':
				verbose = False
			elif arg == '-v':
				verbose = True
			elif arg == '--help':
				printHelp()
				return
			else:
				print('Unknown option: %s' % arg)
				return
		else:
			defaultList.append(arg)
	if not inputFiles and not outputFiles:
		print('No input files specified.')
		return
	if not inputFiles or not outputFiles:
		for file in inputFiles:
			writePUAA(file, None, file, verbose=verbose)
		for file in outputFiles:
			writePUAA(file, None, file, verbose=verbose)
		return
	if len(inputFiles) == 1 and len(outputFiles) == 1:
		writePUAA(inputFiles[0], None, outputFiles[0], verbose=verbose)
		return
	if len(inputFiles) > 1:
		print('Too many input files.')
	if len(outputFiles) > 1:
		print('Too many output files.')

def parseCodePoint(s):
	d = s.encode('utf-32be')
	if len(d) == 4:
		return intStruct.unpack(d)[0]
	try:
		return int(re.sub('[Uu][+]|[0][Xx]|\\s', '', s), 16)
	except:
		print('Invalid code point: %s' % s)
		return None

def lookup(args):
	def printHelp():
		print()
		print('pypuaa lookup - Look up Unicode Character Database properties in TrueType files.')
		print()
		print('  -i <path>     Specify source TrueType file.')
		print('  -p <prop>     Specify properties to look up.')
		print('  -c <cp>       Specify code points to look up.')
		print('  --            Process remaining arguments as code points.')
		print()
	if not args:
		printHelp()
		return
	tables = []
	properties = []
	codePoints = []
	parsingOptions = True
	argi = 0
	while argi < len(args):
		arg = args[argi]
		argi += 1
		if parsingOptions and arg.startswith('-'):
			if arg == '--':
				parsingOptions = False
			elif arg == '-i' and argi < len(args):
				puaa = readPUAA(args[argi])
				if puaa is not None:
					tables += puaa.subtables
				argi += 1
			elif arg == '-p' and argi < len(args):
				prop = args[argi].strip().lower()
				if prop:
					properties.append(prop)
				argi += 1
			elif arg == '-c' and argi < len(args):
				cp = parseCodePoint(args[argi])
				if cp is not None:
					codePoints.append(cp)
				argi += 1
			elif arg == '--help':
				printHelp()
				return
			else:
				print('Unknown option: %s' % arg)
				return
		else:
			cp = parseCodePoint(arg)
			if cp is not None:
				codePoints.append(cp)
	if not tables:
		print('No tables found.')
		return
	if not codePoints:
		if not properties:
			print('Properties:')
			for table in tables:
				print('  %s' % table.propertyName)
			return
		for table in tables:
			if table.propertyName.lower() in properties:
				print('%s:' % table.propertyName)
				for entry in runsFromEntries(table.entries):
					r = '%s:' % joinRange(entry)
					print('  %-16s%s' % (r, entry.value))
		return
	fmt = '  %%-%ds%%s' % (max(len(table.propertyName) for table in tables) + 2)
	for cp in codePoints:
		print('U+%04X:' % cp)
		for table in tables:
			if not properties or table.propertyName.lower() in properties:
				value = table.propertyValue(cp)
				if value is not None:
					p = '%s:' % table.propertyName
					print(fmt % (p, value))

def rewriteTest(args):
	dataFiles = []
	parsingOptions = True
	verbose = True
	argi = 0
	while argi < len(args):
		arg = args[argi]
		argi += 1
		if parsingOptions and arg.startswith('-'):
			if arg == '--':
				parsingOptions = False
			elif arg == '-q':
				verbose = False
			elif arg == '-v':
				verbose = True
			else:
				dataFiles.append(arg)
		else:
			dataFiles.append(arg)
	for file in dataFiles:
		testPUAA(file, verbose=verbose)

def roundTripTest(args):
	dataFiles = []
	parsingOptions = True
	verbose = True
	argi = 0
	while argi < len(args):
		arg = args[argi]
		argi += 1
		if parsingOptions and arg.startswith('-'):
			if arg == '--':
				parsingOptions = False
			elif arg == '-q':
				verbose = False
			elif arg == '-v':
				verbose = True
			else:
				dataFiles.append(arg)
		else:
			dataFiles.append(arg)
	puaa = compilePUAA(dataFiles, verbose=verbose)
	writePUAA(None, puaa, 'out.ucd', verbose=verbose)
	puaa = readPUAA('out.ucd', verbose=verbose)
	decompilePUAA(puaa, 'out', verbose=verbose)

def main():
	def printHelp():
		print()
		print('pypuaa - Manipulate Unicode Character Database properties in TrueType files.')
		print()
		print('  pypuaa compile <args>   - Add UCD properties to TrueType files.')
		print('  pypuaa decompile <args> - Create UCD files from TrueType files.')
		print('  pypuaa copy <args>      - Copy UCD properties across TrueType files.')
		print('  pypuaa strip <args>     - Remove UCD properties from TrueType files.')
		print('  pypuaa lookup <args>    - Look up UCD properties in TrueType files.')
		print()
	args = sys.argv[1:]
	if not args:
		printHelp()
		return
	command = args.pop(0)
	if command == 'help':
		printHelp()
	elif command == 'compile':
		compile(args)
	elif command == 'decompile':
		decompile(args)
	elif command == 'copy':
		copy(args)
	elif command == 'strip':
		strip(args)
	elif command == 'lookup':
		lookup(args)
	elif command == 'rewriteTest':
		rewriteTest(args)
	elif command == 'roundTripTest':
		roundTripTest(args)
	elif command == 'printFileNames':
		printFileNames()
	else:
		print('Unknown command: %s' % command)
		printHelp()

if __name__ == '__main__':
	main()
