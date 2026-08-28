# SINERGY federation — canonical JSON profile v1

Status: **draft canonicalization profile / cross-language conformance contract**.

This profile exists to make content-addressed federation objects reproducible across Python, Node.js and later additional runtimes without relying on language-specific floating-point formatting.

It does not replace domain schemas. It defines the byte-level JSON profile used **after** domain values have already been normalized into their canonical semantic representation.

---

## 1. Two separate layers

SINERGY deliberately separates:

```text
Domain normalization
        ↓
Canonical JSON serialization
        ↓
UTF-8 bytes
        ↓
SHA-256
```

These layers must not be merged.

### Domain normalization

The domain producer decides what a value means and how it must be represented.

For monetary/fractional economic values the preferred representation is a unique decimal string:

```text
0.20   -> "0.2"
1.000  -> "1"
-0.00  -> "0"
0.0010 -> "0.001"
```

This normalization happens **before hashing** and is enforced by the producer/runtime/schema for schemas that opt into the new profile, beginning with `project.proposal/v2`.

### Generic canonical JSON

The generic serializer treats strings as opaque strings.

Therefore:

```text
"0.2"
```

and:

```text
"0.20"
```

are different byte strings and produce different digests at the generic JSON layer.

The generic serializer must never silently rewrite an already supplied string. Doing so would make it impossible to verify the exact bytes of an externally produced object.

---

## 2. Allowed primitive data model

`sinergy.canonical-json/v1` accepts:

- JSON `null`;
- Unicode strings;
- booleans;
- arrays;
- objects with **string keys only**;
- JSON integer numbers only when their magnitude is within the cross-language safe-integer range:

```text
-9007199254740991 .. 9007199254740991
```

The integer-number channel is intended for discrete values such as:

- sequence numbers;
- week horizons;
- counters;
- schema revision integers.

It is not the monetary/fractional channel.

---

## 3. Forbidden primitive values

The canonical profile rejects:

- binary floating-point values;
- `NaN`;
- `+Infinity` / `-Infinity`;
- Python `Decimal` objects that have not yet been converted to canonical decimal text;
- unsafe JSON integers outside the JavaScript safe-integer range;
- non-string object keys;
- runtime-specific non-JSON values such as functions, bytes or arbitrary objects.

The Node.js implementation additionally rejects JavaScript `-0` explicitly instead of allowing `JSON.stringify(-0)` to silently serialize it as `0`.

Domain producers should normalize an economic negative/quantized zero to decimal string:

```text
"0"
```

before it reaches this layer.

---

## 4. Object ordering and byte encoding

Canonical serialization uses:

```text
recursive lexicographic sorting of object keys
compact separators: ',' and ':'
UTF-8
Unicode emitted directly rather than ASCII \u escaping
```

Arrays preserve their declared order.

The profile does not reorder arrays because array order may be semantically meaningful.

---

## 5. Unicode policy

Version 1 does **not** perform Unicode normalization such as NFC/NFD conversion.

Reason:

```text
content identity != visual similarity
```

Two different Unicode code-point sequences remain different content unless the **domain producer** explicitly normalizes a particular field before serialization.

This avoids a generic hash layer silently changing externally supplied identifiers, legal names or evidence text.

If a future schema requires normalized identifiers, that rule belongs in that schema/domain producer and must receive its own versioned migration.

---

## 6. Decimal policy

The shared Financial OS helper:

```text
canonical_decimal_text(value)
```

returns the unique non-exponent representation of a finite Decimal without rounding.

Examples:

```text
Decimal('0.20')    -> "0.2"
Decimal('1.000')   -> "1"
Decimal('-0.00')   -> "0"
Decimal('1000')    -> "1000"
Decimal('-12.340') -> "-12.34"
```

A domain schema that adopts unique decimal text should reject alternative textual spellings such as:

```text
"01"
"1.0"
"0.20"
"-0"
"1e-3"
```

when the canonical forms are respectively:

```text
"1"
"1"
"0.2"
"0"
"0.001"
```

`project.proposal/v2` is the first project-domain schema hardened to this rule while `project.proposal/v1` remains preserved as historical provenance.

---

## 7. Reference serialization

For this semantic payload:

```json
{
  "z": "Привет",
  "a": [3, {"b": null, "a": "x"}],
  "n": 7,
  "s": "1.23",
  "bool": true
}
```

canonical JSON text is exactly:

```text
{"a":[3,{"a":"x","b":null}],"bool":true,"n":7,"s":"1.23","z":"Привет"}
```

The same vector is stored in both:

```text
Shtenco/synergy_financial_os
fixtures/conformance/canonical_json_v1_unicode_safe_integer.json

Shtenco/synergychain
financial_os_v8/conformance/canonical_json_v1_unicode_safe_integer.json
```

The Python root and Node control-plane implementation must produce byte-identical canonical text for this vector.

---

## 8. Current implementations

Canonical root:

```text
sinergy_financial_os/canonical_json.py
sinergy_financial_os/numeric.py
tests/test_canonical_json.py
```

Node read-only consumer:

```text
financial_os_v8/canonical_json_v1.cjs
financial_os_v8/test_canonical_json_conformance.cjs
```

The actual FinancialSnapshot v2 portal verifier consumes the shared Node canonical serializer rather than a demonstration-only copy.

---

## 9. What this profile does not prove

A valid canonical digest proves only content identity under the declared byte profile.

It does not prove:

- authenticity;
- legal authority;
- economic correctness;
- asset existence;
- external settlement;
- audit status;
- authorization to execute.

Those belong to schema semantics, evidence, signatures/HSM policy, accounting controls and governance.

---

## 10. Migration rule

Do not silently retrofit a stronger decimal/JSON canonicalization rule into an already promoted immutable schema.

Preferred migration pattern:

```text
old schema preserved
       ↓
new schema version introduced side-by-side
       ↓
producer exports both during transition when needed
       ↓
new canonical commitments accept only the hardened version
```

This is the exact pattern currently used for:

```text
project.proposal/v1 -> project.proposal/v2
```

The trust layer preserves v1 provenance but allows new `PROJECT_PROPOSAL` commitments only for v2.

---

## 11. Verification status

The profile, implementations and conformance vectors are **ADDRESSED / PENDING_RUNNER** until configured CI runners actually execute the mapped Python and Node tests.

Workflow presence is not test evidence.
