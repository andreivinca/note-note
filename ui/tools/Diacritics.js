.pragma library

// Common Latin alphabets. Keep both cases explicit: German ß and Turkish
// dotless/dotted i cannot use JavaScript's language-independent uppercasing.
var alphabets = {
  bs: { lower: "čćđšž", upper: "ČĆĐŠŽ" },
  ca: { lower: "àçèéíïòóúü", upper: "ÀÇÈÉÍÏÒÓÚÜ" },
  cs: { lower: "áčďéěíňóřšťúůýž", upper: "ÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ" },
  cy: { lower: "âêîôûŵŷ", upper: "ÂÊÎÔÛŴŶ" },
  da: { lower: "æøå", upper: "ÆØÅ" },
  de: { lower: "äöüß", upper: "ÄÖÜẞ" },
  es: { lower: "áéíñóúü", upper: "ÁÉÍÑÓÚÜ" },
  et: { lower: "äöõü", upper: "ÄÖÕÜ" },
  fi: { lower: "äöå", upper: "ÄÖÅ" },
  fr: { lower: "àâæçéèêëîïôœùûüÿ", upper: "ÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ" },
  ga: { lower: "áéíóú", upper: "ÁÉÍÓÚ" },
  hr: { lower: "čćđšž", upper: "ČĆĐŠŽ" },
  hu: { lower: "áéíóöőúüű", upper: "ÁÉÍÓÖŐÚÜŰ" },
  is: { lower: "áðéíóúýþæö", upper: "ÁÐÉÍÓÚÝÞÆÖ" },
  it: { lower: "àèéìòóù", upper: "ÀÈÉÌÒÓÙ" },
  lb: { lower: "äéë", upper: "ÄÉË" },
  lt: { lower: "ąčęėįšųūž", upper: "ĄČĘĖĮŠŲŪŽ" },
  lv: { lower: "āčēģīķļņšūž", upper: "ĀČĒĢĪĶĻŅŠŪŽ" },
  mt: { lower: "ċġħż", upper: "ĊĠĦŻ" },
  nb: { lower: "æøå", upper: "ÆØÅ" },
  nl: { lower: "áéëíïóöúü", upper: "ÁÉËÍÏÓÖÚÜ" },
  nn: { lower: "æøå", upper: "ÆØÅ" },
  pl: { lower: "ąćęłńóśźż", upper: "ĄĆĘŁŃÓŚŹŻ" },
  pt: { lower: "áâãàçéêíóôõú", upper: "ÁÂÃÀÇÉÊÍÓÔÕÚ" },
  ro: { lower: "ăâîșț", upper: "ĂÂÎȘȚ" },
  sk: { lower: "áäčďéíĺľňóôŕšťúýž", upper: "ÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ" },
  sl: { lower: "čšž", upper: "ČŠŽ" },
  sq: { lower: "çë", upper: "ÇË" },
  sv: { lower: "åäö", upper: "ÅÄÖ" },
  tr: { lower: "çğıöşü", upper: "ÇĞİÖŞÜ" }
}

// The system timezone identifies a country independently of the interface
// language. Use that country's default Latin alphabet when it has one.
var regionLanguages = {
  AL: "sq", AT: "de", BA: "bs", BE: "nl", BR: "pt", CA: "fr", CH: "de",
  CZ: "cs", DE: "de", DK: "da", EE: "et", ES: "es", FI: "fi", FR: "fr",
  HR: "hr", HU: "hu", IE: "ga", IS: "is", IT: "it", LI: "de", LT: "lt",
  LU: "lb", LV: "lv", MC: "fr", MD: "ro", MT: "mt", NL: "nl", NO: "nb",
  PL: "pl", PT: "pt", RO: "ro", SE: "sv", SI: "sl", SK: "sk", TR: "tr",
  AR: "es", BO: "es", CL: "es", CO: "es", CR: "es", CU: "es", DO: "es",
  EC: "es", GT: "es", HN: "es", MX: "es", NI: "es", PA: "es", PE: "es",
  PR: "es", PY: "es", SV: "es", UY: "es", VE: "es"
}

function alphabet(countryCode) {
  var region = String(countryCode || "").toUpperCase()
  if (!/^[A-Z]{2}$/.test(region)) {
    return null
  }
  var selected = regionLanguages[region]
  if (!selected || !alphabets[selected]) {
    return null
  }
  var letters = alphabets[selected]
  if (selected === "de" && (region === "CH" || region === "LI")) {
    letters = { lower: "äöü", upper: "ÄÖÜ" }
  }
  return { language: selected, lower: letters.lower, upper: letters.upper }
}
