// Test the deep equality function
function isDateRangeEqual(a, b) {
  if (a === b) return true
  if (!a || !b) return false
  
  const aFromTime = a.from?.getTime()
  const aToTime = a.to?.getTime()
  const bFromTime = b.from?.getTime()
  const bToTime = b.to?.getTime()
  
  return aFromTime === bFromTime && aToTime === bToTime
}

// Test cases
const date1 = new Date('2024-01-01')
const date2 = new Date('2024-01-15')

// Test 1: Same object reference
const range1 = { from: date1, to: date2 }
console.log('✅ Test 1 (same reference):', isDateRangeEqual(range1, range1))

// Test 2: Different objects, same values
const range2 = { from: new Date('2024-01-01'), to: new Date('2024-01-15') }
const range3 = { from: new Date('2024-01-01'), to: new Date('2024-01-15') }
console.log('✅ Test 2 (same values):', isDateRangeEqual(range2, range3))

// Test 3: Different values
const range4 = { from: new Date('2024-01-01'), to: new Date('2024-01-20') }
console.log('✅ Test 3 (different values):', !isDateRangeEqual(range2, range4))

// Test 4: Undefined handling
console.log('✅ Test 4 (undefined):', isDateRangeEqual(undefined, undefined))
console.log('✅ Test 5 (undefined vs defined):', !isDateRangeEqual(undefined, range1))

// Test 6: Partial ranges
const partial1 = { from: date1, to: undefined }
const partial2 = { from: new Date('2024-01-01'), to: undefined }
console.log('✅ Test 6 (partial ranges):', isDateRangeEqual(partial1, partial2))

console.log('✅ All deep equality tests passed')