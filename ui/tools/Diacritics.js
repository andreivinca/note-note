.pragma library

// Common Latin alphabets, each named in its own language. Keep both cases
// explicit: German ß and Turkish dotless/dotted i cannot use JavaScript's
// language-independent uppercasing.
var alphabets = {
  bs: { name: "Bosanski", lower: "čćđšž", upper: "ČĆĐŠŽ" },
  ca: { name: "Català", lower: "àçèéíïòóúü", upper: "ÀÇÈÉÍÏÒÓÚÜ" },
  cs: { name: "Čeština", lower: "áčďéěíňóřšťúůýž", upper: "ÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ" },
  cy: { name: "Cymraeg", lower: "âêîôûŵŷ", upper: "ÂÊÎÔÛŴŶ" },
  da: { name: "Dansk", lower: "æøå", upper: "ÆØÅ" },
  de: { name: "Deutsch", lower: "äöüß", upper: "ÄÖÜẞ" },
  // Swiss Standard German writes ss in place of ß.
  de_CH: { name: "Deutsch (Schweiz)", lower: "äöü", upper: "ÄÖÜ" },
  es: { name: "Español", lower: "áéíñóúü", upper: "ÁÉÍÑÓÚÜ" },
  et: { name: "Eesti", lower: "äöõü", upper: "ÄÖÕÜ" },
  fi: { name: "Suomi", lower: "äöå", upper: "ÄÖÅ" },
  fr: { name: "Français", lower: "àâæçéèêëîïôœùûüÿ", upper: "ÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ" },
  ga: { name: "Gaeilge", lower: "áéíóú", upper: "ÁÉÍÓÚ" },
  hr: { name: "Hrvatski", lower: "čćđšž", upper: "ČĆĐŠŽ" },
  hu: { name: "Magyar", lower: "áéíóöőúüű", upper: "ÁÉÍÓÖŐÚÜŰ" },
  is: { name: "Íslenska", lower: "áðéíóúýþæö", upper: "ÁÐÉÍÓÚÝÞÆÖ" },
  it: { name: "Italiano", lower: "àèéìòóù", upper: "ÀÈÉÌÒÓÙ" },
  lb: { name: "Lëtzebuergesch", lower: "äéë", upper: "ÄÉË" },
  lt: { name: "Lietuvių", lower: "ąčęėįšųūž", upper: "ĄČĘĖĮŠŲŪŽ" },
  lv: { name: "Latviešu", lower: "āčēģīķļņšūž", upper: "ĀČĒĢĪĶĻŅŠŪŽ" },
  mt: { name: "Malti", lower: "ċġħż", upper: "ĊĠĦŻ" },
  nb: { name: "Norsk bokmål", lower: "æøå", upper: "ÆØÅ" },
  nl: { name: "Nederlands", lower: "áéëíïóöúü", upper: "ÁÉËÍÏÓÖÚÜ" },
  nn: { name: "Norsk nynorsk", lower: "æøå", upper: "ÆØÅ" },
  pl: { name: "Polski", lower: "ąćęłńóśźż", upper: "ĄĆĘŁŃÓŚŹŻ" },
  pt: { name: "Português", lower: "áâãàçéêíóôõú", upper: "ÁÂÃÀÇÉÊÍÓÔÕÚ" },
  ro: { name: "Română", lower: "ăâîșț", upper: "ĂÂÎȘȚ" },
  sk: { name: "Slovenčina", lower: "áäčďéíĺľňóôŕšťúýž", upper: "ÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ" },
  sl: { name: "Slovenščina", lower: "čšž", upper: "ČŠŽ" },
  sq: { name: "Shqip", lower: "çë", upper: "ÇË" },
  sv: { name: "Svenska", lower: "åäö", upper: "ÅÄÖ" },
  tr: { name: "Türkçe", lower: "çğıöşü", upper: "ÇĞİÖŞÜ" }
}

// The system timezone identifies a country independently of the interface
// language. It suggests that country's default Latin alphabet, if it has one.
var regionLanguages = {
  AL: "sq", AT: "de", BA: "bs", BE: "nl", BR: "pt", CA: "fr", CH: "de_CH",
  CZ: "cs", DE: "de", DK: "da", EE: "et", ES: "es", FI: "fi", FR: "fr",
  HR: "hr", HU: "hu", IE: "ga", IS: "is", IT: "it", LI: "de_CH", LT: "lt",
  LU: "lb", LV: "lv", MC: "fr", MD: "ro", MT: "mt", NL: "nl", NO: "nb",
  PL: "pl", PT: "pt", RO: "ro", SE: "sv", SI: "sl", SK: "sk", TR: "tr",
  AR: "es", BO: "es", CL: "es", CO: "es", CR: "es", CU: "es", DO: "es",
  EC: "es", GT: "es", HN: "es", MX: "es", NI: "es", PA: "es", PE: "es",
  PR: "es", PY: "es", SV: "es", UY: "es", VE: "es"
}

// Every alphabet as a choice, ordered by its name.
function languages() {
  return Object.keys(alphabets).map(function(language) {
    return { value: language, label: alphabets[language].name }
  }).sort(function(a, b) {
    return a.label.localeCompare(b.label)
  })
}

// The language a country suggests, or "" when it has no supported alphabet.
function regionLanguage(countryCode) {
  var region = String(countryCode || "").toUpperCase()
  if (!/^[A-Z]{2}$/.test(region) || !Object.prototype.hasOwnProperty.call(regionLanguages, region)) {
    return ""
  }
  return regionLanguages[region]
}

function alphabet(language) {
  if (!Object.prototype.hasOwnProperty.call(alphabets, language)) {
    return null
  }
  return alphabets[language]
}
