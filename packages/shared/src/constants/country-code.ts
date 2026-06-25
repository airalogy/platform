import type { Component } from "vue"

import IconAfghanistan from "~icons/twemoji/flag-afghanistan"
import IconAlbania from "~icons/twemoji/flag-albania"
import IconAlgeria from "~icons/twemoji/flag-algeria"
import IconAmericanSamoa from "~icons/twemoji/flag-american-samoa"
import IconAndorra from "~icons/twemoji/flag-andorra"
import IconAngola from "~icons/twemoji/flag-angola"
import IconAnguilla from "~icons/twemoji/flag-anguilla"
import IconAntarctica from "~icons/twemoji/flag-antarctica"
import IconAntiguaAndBarbuda from "~icons/twemoji/flag-antigua-and-barbuda"
import IconArgentina from "~icons/twemoji/flag-argentina"
import IconArmenia from "~icons/twemoji/flag-armenia"
import IconAruba from "~icons/twemoji/flag-aruba"
import IconAustralia from "~icons/twemoji/flag-australia"
import IconAustria from "~icons/twemoji/flag-austria"
import IconAzerbaijan from "~icons/twemoji/flag-azerbaijan"
import IconBahamas from "~icons/twemoji/flag-bahamas"
import IconBahrain from "~icons/twemoji/flag-bahrain"
import IconBangladesh from "~icons/twemoji/flag-bangladesh"
import IconBarbados from "~icons/twemoji/flag-barbados"
import IconBelarus from "~icons/twemoji/flag-belarus"
import IconBelgium from "~icons/twemoji/flag-belgium"
import IconBelize from "~icons/twemoji/flag-belize"
import IconBenin from "~icons/twemoji/flag-benin"
import IconBermuda from "~icons/twemoji/flag-bermuda"
import IconBhutan from "~icons/twemoji/flag-bhutan"
import IconBolivia from "~icons/twemoji/flag-bolivia"
import IconBosniaAndHerzegovina from "~icons/twemoji/flag-bosnia-and-herzegovina"
import IconBotswana from "~icons/twemoji/flag-botswana"
import IconBrazil from "~icons/twemoji/flag-brazil"
import IconBritishIndianOceanTerritory from "~icons/twemoji/flag-british-indian-ocean-territory"
import IconBrunei from "~icons/twemoji/flag-brunei"
import IconBulgaria from "~icons/twemoji/flag-bulgaria"
import IconBurkinaFaso from "~icons/twemoji/flag-burkina-faso"
import IconBurundi from "~icons/twemoji/flag-burundi"
import IconCambodia from "~icons/twemoji/flag-cambodia"
import IconCameroon from "~icons/twemoji/flag-cameroon"
import IconCanada from "~icons/twemoji/flag-canada"
import IconCapeVerde from "~icons/twemoji/flag-cape-verde"
import IconCaymanIslands from "~icons/twemoji/flag-cayman-islands"
import IconCentralAfricanRepublic from "~icons/twemoji/flag-central-african-republic"
import IconChad from "~icons/twemoji/flag-chad"
import IconChile from "~icons/twemoji/flag-chile"
import IconChina from "~icons/twemoji/flag-china"
import IconChristmasIsland from "~icons/twemoji/flag-christmas-island"
import IconCocosIslands from "~icons/twemoji/flag-cocos-keeling-islands"
import IconColombia from "~icons/twemoji/flag-colombia"
import IconComoros from "~icons/twemoji/flag-comoros"
import IconRepublicOfTheCongo from "~icons/twemoji/flag-congo-brazzaville"
import IconDemocraticRepublicOfTheCongo from "~icons/twemoji/flag-congo-kinshasa"
import IconCookIslands from "~icons/twemoji/flag-cook-islands"
import IconCostaRica from "~icons/twemoji/flag-costa-rica"
import IconCroatia from "~icons/twemoji/flag-croatia"
import IconCuba from "~icons/twemoji/flag-cuba"
import IconCuracao from "~icons/twemoji/flag-curacao"
import IconCyprus from "~icons/twemoji/flag-cyprus"
import IconCzechRepublic from "~icons/twemoji/flag-czechia"
import IconDenmark from "~icons/twemoji/flag-denmark"
import IconDjibouti from "~icons/twemoji/flag-djibouti"
import IconDominica from "~icons/twemoji/flag-dominica"
import IconDominicanRepublic from "~icons/twemoji/flag-dominican-republic"
import IconEcuador from "~icons/twemoji/flag-ecuador"
import IconEgypt from "~icons/twemoji/flag-egypt"
import IconElSalvador from "~icons/twemoji/flag-el-salvador"
import IconEquatorialGuinea from "~icons/twemoji/flag-equatorial-guinea"
import IconEritrea from "~icons/twemoji/flag-eritrea"
import IconEstonia from "~icons/twemoji/flag-estonia"
import IconEswatini from "~icons/twemoji/flag-eswatini"
import IconEthiopia from "~icons/twemoji/flag-ethiopia"
import IconFalklandIslands from "~icons/twemoji/flag-falkland-islands"
import IconFaroeIslands from "~icons/twemoji/flag-faroe-islands"
import IconFiji from "~icons/twemoji/flag-fiji"
import IconFinland from "~icons/twemoji/flag-finland"
import IconFrance from "~icons/twemoji/flag-france"
import IconFrenchPolynesia from "~icons/twemoji/flag-french-polynesia"
import IconGabon from "~icons/twemoji/flag-gabon"
import IconGambia from "~icons/twemoji/flag-gambia"
import IconGeorgia from "~icons/twemoji/flag-georgia"
import IconGermany from "~icons/twemoji/flag-germany"
import IconGhana from "~icons/twemoji/flag-ghana"
import IconGibraltar from "~icons/twemoji/flag-gibraltar"
import IconGreece from "~icons/twemoji/flag-greece"
import IconGreenland from "~icons/twemoji/flag-greenland"
import IconGrenada from "~icons/twemoji/flag-grenada"
import IconGuam from "~icons/twemoji/flag-guam"
import IconGuatemala from "~icons/twemoji/flag-guatemala"
import IconGuinea from "~icons/twemoji/flag-guinea"
import IconGuineaBissau from "~icons/twemoji/flag-guinea-bissau"
import IconGuyana from "~icons/twemoji/flag-guyana"
import IconHaiti from "~icons/twemoji/flag-haiti"
import IconHonduras from "~icons/twemoji/flag-honduras"
import IconHongKong from "~icons/twemoji/flag-hong-kong-sar-china"
import IconHungary from "~icons/twemoji/flag-hungary"
import IconIceland from "~icons/twemoji/flag-iceland"
import IconIndia from "~icons/twemoji/flag-india"
import IconIndonesia from "~icons/twemoji/flag-indonesia"
import IconIran from "~icons/twemoji/flag-iran"
import IconIraq from "~icons/twemoji/flag-iraq"
import IconIreland from "~icons/twemoji/flag-ireland"
import IconIsrael from "~icons/twemoji/flag-israel"
import IconItaly from "~icons/twemoji/flag-italy"
import IconPapuaNewGuinea from "~icons/twemoji/flag-papua-new-guinea"
// import IconIvoryCoast from "~icons/twemoji/flag-ivory-coast"
import IconJamaica from "~icons/twemoji/flag-jamaica"
import IconJapan from "~icons/twemoji/flag-japan"
import IconJordan from "~icons/twemoji/flag-jordan"
import IconKazakhstan from "~icons/twemoji/flag-kazakhstan"
import IconKenya from "~icons/twemoji/flag-kenya"
import IconKiribati from "~icons/twemoji/flag-kiribati"
import IconKosovo from "~icons/twemoji/flag-kosovo"
import IconKuwait from "~icons/twemoji/flag-kuwait"
import IconKyrgyzstan from "~icons/twemoji/flag-kyrgyzstan"
import IconLaos from "~icons/twemoji/flag-laos"
import IconLatvia from "~icons/twemoji/flag-latvia"
import IconLebanon from "~icons/twemoji/flag-lebanon"
import IconLesotho from "~icons/twemoji/flag-lesotho"
import IconLiberia from "~icons/twemoji/flag-liberia"
import IconLibya from "~icons/twemoji/flag-libya"
import IconLiechtenstein from "~icons/twemoji/flag-liechtenstein"
import IconLithuania from "~icons/twemoji/flag-lithuania"
import IconLuxembourg from "~icons/twemoji/flag-luxembourg"
import IconMacao from "~icons/twemoji/flag-macao-sar-china"
import IconMadagascar from "~icons/twemoji/flag-madagascar"
import IconMalawi from "~icons/twemoji/flag-malawi"
import IconMalaysia from "~icons/twemoji/flag-malaysia"
import IconMaldives from "~icons/twemoji/flag-maldives"
import IconMali from "~icons/twemoji/flag-mali"
import IconMalta from "~icons/twemoji/flag-malta"
import IconMarshallIslands from "~icons/twemoji/flag-marshall-islands"
import IconMauritania from "~icons/twemoji/flag-mauritania"
import IconMauritius from "~icons/twemoji/flag-mauritius"
import IconMayotte from "~icons/twemoji/flag-mayotte"
import IconMexico from "~icons/twemoji/flag-mexico"
import IconMicronesia from "~icons/twemoji/flag-micronesia"
import IconMoldova from "~icons/twemoji/flag-moldova"
import IconMonaco from "~icons/twemoji/flag-monaco"
import IconMongolia from "~icons/twemoji/flag-mongolia"
import IconMontenegro from "~icons/twemoji/flag-montenegro"
import IconMorocco from "~icons/twemoji/flag-morocco"
import IconMozambique from "~icons/twemoji/flag-mozambique"
import IconMyanmar from "~icons/twemoji/flag-myanmar-burma"
import IconNamibia from "~icons/twemoji/flag-namibia"
import IconNauru from "~icons/twemoji/flag-nauru"
import IconNepal from "~icons/twemoji/flag-nepal"
import IconNetherlands from "~icons/twemoji/flag-netherlands"
import IconNewCaledonia from "~icons/twemoji/flag-new-caledonia"
import IconNewZealand from "~icons/twemoji/flag-new-zealand"
import IconNicaragua from "~icons/twemoji/flag-nicaragua"
import IconNiger from "~icons/twemoji/flag-niger"
import IconNigeria from "~icons/twemoji/flag-nigeria"
import IconNiue from "~icons/twemoji/flag-niue"
import IconNorthKorea from "~icons/twemoji/flag-north-korea"
import IconMacedonia from "~icons/twemoji/flag-north-macedonia"
import IconNorthernMarianaIslands from "~icons/twemoji/flag-northern-mariana-islands"
import IconNorway from "~icons/twemoji/flag-norway"
import IconOman from "~icons/twemoji/flag-oman"
import IconPakistan from "~icons/twemoji/flag-pakistan"
import IconPalau from "~icons/twemoji/flag-palau"
import IconPalestine from "~icons/twemoji/flag-palestinian-territories"
import IconPanama from "~icons/twemoji/flag-panama"
import IconParaguay from "~icons/twemoji/flag-paraguay"
import IconPeru from "~icons/twemoji/flag-peru"
import IconPhilippines from "~icons/twemoji/flag-philippines"
import IconPoland from "~icons/twemoji/flag-poland"
import IconPortugal from "~icons/twemoji/flag-portugal"
import IconPuertoRico from "~icons/twemoji/flag-puerto-rico"
import IconQatar from "~icons/twemoji/flag-qatar"
import IconRomania from "~icons/twemoji/flag-romania"
import IconRussia from "~icons/twemoji/flag-russia"
import IconRwanda from "~icons/twemoji/flag-rwanda"
import IconSamoa from "~icons/twemoji/flag-samoa"
import IconSanMarino from "~icons/twemoji/flag-san-marino"
import IconSaoTomeAndPrincipe from "~icons/twemoji/flag-sao-tome-and-principe"
import IconSaudiArabia from "~icons/twemoji/flag-saudi-arabia"
import IconSenegal from "~icons/twemoji/flag-senegal"
import IconSerbia from "~icons/twemoji/flag-serbia"
import IconSeychelles from "~icons/twemoji/flag-seychelles"
import IconSierraLeone from "~icons/twemoji/flag-sierra-leone"
import IconSingapore from "~icons/twemoji/flag-singapore"
import IconSintMaarten from "~icons/twemoji/flag-sint-maarten"
import IconSlovakia from "~icons/twemoji/flag-slovakia"
import IconSlovenia from "~icons/twemoji/flag-slovenia"
import IconSolomonIslands from "~icons/twemoji/flag-solomon-islands"
import IconSomalia from "~icons/twemoji/flag-somalia"
import IconSouthAfrica from "~icons/twemoji/flag-south-africa"
import IconSouthKorea from "~icons/twemoji/flag-south-korea"
import IconSouthSudan from "~icons/twemoji/flag-south-sudan"
import IconSpain from "~icons/twemoji/flag-spain"
import IconSriLanka from "~icons/twemoji/flag-sri-lanka"
import IconSaintHelena from "~icons/twemoji/flag-st-helena"
import IconSaintKittsAndNevis from "~icons/twemoji/flag-st-kitts-and-nevis"
import IconSaintLucia from "~icons/twemoji/flag-st-lucia"
import IconSaintPierreAndMiquelon from "~icons/twemoji/flag-st-pierre-and-miquelon"
import IconSaintVincentAndTheGrenadines from "~icons/twemoji/flag-st-vincent-and-grenadines"
import IconSudan from "~icons/twemoji/flag-sudan"
import IconSuriname from "~icons/twemoji/flag-suriname"
import IconSweden from "~icons/twemoji/flag-sweden"
import IconSwitzerland from "~icons/twemoji/flag-switzerland"
import IconSyria from "~icons/twemoji/flag-syria"
import IconTaiwan from "~icons/twemoji/flag-taiwan"
import IconTajikistan from "~icons/twemoji/flag-tajikistan"
import IconTanzania from "~icons/twemoji/flag-tanzania"
import IconThailand from "~icons/twemoji/flag-thailand"
import IconEastTimor from "~icons/twemoji/flag-timor-leste"
import IconTogo from "~icons/twemoji/flag-togo"
import IconTokelau from "~icons/twemoji/flag-tokelau"
import IconTonga from "~icons/twemoji/flag-tonga"
import IconTrinidadAndTobago from "~icons/twemoji/flag-trinidad-and-tobago"
import IconTunisia from "~icons/twemoji/flag-tunisia"
import IconTurkey from "~icons/twemoji/flag-turkey"
import IconTurkmenistan from "~icons/twemoji/flag-turkmenistan"
import IconTurksAndCaicosIslands from "~icons/twemoji/flag-turks-and-caicos-islands"
import IconTuvalu from "~icons/twemoji/flag-tuvalu"
import IconUganda from "~icons/twemoji/flag-uganda"
import IconUkraine from "~icons/twemoji/flag-ukraine"
import IconUnitedArabEmirates from "~icons/twemoji/flag-united-arab-emirates"
import IconUnitedKingdom from "~icons/twemoji/flag-united-kingdom"
import IconUnitedStates from "~icons/twemoji/flag-united-states"
import IconUruguay from "~icons/twemoji/flag-uruguay"
import IconUzbekistan from "~icons/twemoji/flag-uzbekistan"
import IconVanuatu from "~icons/twemoji/flag-vanuatu"
import IconVatican from "~icons/twemoji/flag-vatican-city"
import IconVenezuela from "~icons/twemoji/flag-venezuela"
import IconVietnam from "~icons/twemoji/flag-vietnam"
import IconWallisAndFutuna from "~icons/twemoji/flag-wallis-and-futuna"
import IconWesternSahara from "~icons/twemoji/flag-western-sahara"
import IconYemen from "~icons/twemoji/flag-yemen"
import IconZambia from "~icons/twemoji/flag-zambia"
import IconZimbabwe from "~icons/twemoji/flag-zimbabwe"

export interface CountryData {
  name: string
  dialCode: string
  isoCode: string
  flag?: string
  icon?: Component
}

// Country data - comprehensive list from research
export const countryData: CountryData[] = [
  { name: "Afghanistan", dialCode: "+93", isoCode: "AF", icon: IconAfghanistan },
  { name: "Albania", dialCode: "+355", isoCode: "AL", icon: IconAlbania },
  { name: "Algeria", dialCode: "+213", isoCode: "DZ", icon: IconAlgeria },
  { name: "American Samoa", dialCode: "+1684", isoCode: "AS", icon: IconAmericanSamoa },
  { name: "Andorra", dialCode: "+376", isoCode: "AD", icon: IconAndorra },
  { name: "Angola", dialCode: "+244", isoCode: "AO", icon: IconAngola },
  { name: "Anguilla", dialCode: "+1264", isoCode: "AI", icon: IconAnguilla },
  { name: "Antarctica", dialCode: "+672", isoCode: "AQ", icon: IconAntarctica },
  { name: "Antigua and Barbuda", dialCode: "+1268", isoCode: "AG", icon: IconAntiguaAndBarbuda },
  { name: "Argentina", dialCode: "+54", isoCode: "AR", icon: IconArgentina },
  { name: "Armenia", dialCode: "+374", isoCode: "AM", icon: IconArmenia },
  { name: "Aruba", dialCode: "+297", isoCode: "AW", icon: IconAruba },
  { name: "Australia", dialCode: "+61", isoCode: "AU", icon: IconAustralia },
  { name: "Austria", dialCode: "+43", isoCode: "AT", icon: IconAustria },
  { name: "Azerbaijan", dialCode: "+994", isoCode: "AZ", icon: IconAzerbaijan },
  { name: "Bahamas", dialCode: "+1242", isoCode: "BS", icon: IconBahamas },
  { name: "Bahrain", dialCode: "+973", isoCode: "BH", icon: IconBahrain },
  { name: "Bangladesh", dialCode: "+880", isoCode: "BD", icon: IconBangladesh },
  { name: "Barbados", dialCode: "+1246", isoCode: "BB", icon: IconBarbados },
  { name: "Belarus", dialCode: "+375", isoCode: "BY", icon: IconBelarus },
  { name: "Belgium", dialCode: "+32", isoCode: "BE", icon: IconBelgium },
  { name: "Belize", dialCode: "+501", isoCode: "BZ", icon: IconBelize },
  { name: "Benin", dialCode: "+229", isoCode: "BJ", icon: IconBenin },
  { name: "Bermuda", dialCode: "+1441", isoCode: "BM", icon: IconBermuda },
  { name: "Bhutan", dialCode: "+975", isoCode: "BT", icon: IconBhutan },
  { name: "Bolivia", dialCode: "+591", isoCode: "BO", icon: IconBolivia },
  { name: "Bosnia and Herzegovina", dialCode: "+387", isoCode: "BA", icon: IconBosniaAndHerzegovina },
  { name: "Botswana", dialCode: "+267", isoCode: "BW", icon: IconBotswana },
  { name: "Brazil", dialCode: "+55", isoCode: "BR", icon: IconBrazil },
  { name: "British Indian Ocean Territory", dialCode: "+246", isoCode: "IO", icon: IconBritishIndianOceanTerritory },
  { name: "Brunei", dialCode: "+673", isoCode: "BN", icon: IconBrunei },
  { name: "Bulgaria", dialCode: "+359", isoCode: "BG", icon: IconBulgaria },
  { name: "Burkina Faso", dialCode: "+226", isoCode: "BF", icon: IconBurkinaFaso },
  { name: "Burundi", dialCode: "+257", isoCode: "BI", icon: IconBurundi },
  { name: "Cambodia", dialCode: "+855", isoCode: "KH", icon: IconCambodia },
  { name: "Cameroon", dialCode: "+237", isoCode: "CM", icon: IconCameroon },
  { name: "Canada", dialCode: "+1", isoCode: "CA", icon: IconCanada },
  { name: "Cape Verde", dialCode: "+238", isoCode: "CV", icon: IconCapeVerde },
  { name: "Cayman Islands", dialCode: "+1345", isoCode: "KY", icon: IconCaymanIslands },
  { name: "Central African Republic", dialCode: "+236", isoCode: "CF", icon: IconCentralAfricanRepublic },
  { name: "Chad", dialCode: "+235", isoCode: "TD", icon: IconChad },
  { name: "Chile", dialCode: "+56", isoCode: "CL", icon: IconChile },
  { name: "China", dialCode: "+86", isoCode: "CN", icon: IconChina },
  { name: "Christmas Island", dialCode: "+61", isoCode: "CX", icon: IconChristmasIsland },
  { name: "Cocos Islands", dialCode: "+61", isoCode: "CC", icon: IconCocosIslands },
  { name: "Colombia", dialCode: "+57", isoCode: "CO", icon: IconColombia },
  { name: "Comoros", dialCode: "+269", isoCode: "KM", icon: IconComoros },
  { name: "Cook Islands", dialCode: "+682", isoCode: "CK", icon: IconCookIslands },
  { name: "Costa Rica", dialCode: "+506", isoCode: "CR", icon: IconCostaRica },
  { name: "Croatia", dialCode: "+385", isoCode: "HR", icon: IconCroatia },
  { name: "Cuba", dialCode: "+53", isoCode: "CU", icon: IconCuba },
  { name: "Curacao", dialCode: "+599", isoCode: "CW", icon: IconCuracao },
  { name: "Cyprus", dialCode: "+357", isoCode: "CY", icon: IconCyprus },
  { name: "Czech Republic", dialCode: "+420", isoCode: "CZ", icon: IconCzechRepublic },
  { name: "Democratic Republic of the Congo", dialCode: "+243", isoCode: "CD", icon: IconDemocraticRepublicOfTheCongo },
  { name: "Denmark", dialCode: "+45", isoCode: "DK", icon: IconDenmark },
  { name: "Djibouti", dialCode: "+253", isoCode: "DJ", icon: IconDjibouti },
  { name: "Dominica", dialCode: "+1767", isoCode: "DM", icon: IconDominica },
  { name: "Dominican Republic", dialCode: "+1849", isoCode: "DO", icon: IconDominicanRepublic },
  { name: "East Timor", dialCode: "+670", isoCode: "TL", icon: IconEastTimor },
  { name: "Ecuador", dialCode: "+593", isoCode: "EC", icon: IconEcuador },
  { name: "Egypt", dialCode: "+20", isoCode: "EG", icon: IconEgypt },
  { name: "El Salvador", dialCode: "+503", isoCode: "SV", icon: IconElSalvador },
  { name: "Equatorial Guinea", dialCode: "+240", isoCode: "GQ", icon: IconEquatorialGuinea },
  { name: "Eritrea", dialCode: "+291", isoCode: "ER", icon: IconEritrea },
  { name: "Estonia", dialCode: "+372", isoCode: "EE", icon: IconEstonia },
  { name: "Ethiopia", dialCode: "+251", isoCode: "ET", icon: IconEthiopia },
  { name: "Falkland Islands", dialCode: "+500", isoCode: "FK", icon: IconFalklandIslands },
  { name: "Faroe Islands", dialCode: "+298", isoCode: "FO", icon: IconFaroeIslands },
  { name: "Fiji", dialCode: "+679", isoCode: "FJ", icon: IconFiji },
  { name: "Finland", dialCode: "+358", isoCode: "FI", icon: IconFinland },
  { name: "France", dialCode: "+33", isoCode: "FR", icon: IconFrance },
  { name: "French Polynesia", dialCode: "+689", isoCode: "PF", icon: IconFrenchPolynesia },
  { name: "Gabon", dialCode: "+241", isoCode: "GA", icon: IconGabon },
  { name: "Gambia", dialCode: "+220", isoCode: "GM", icon: IconGambia },
  { name: "Georgia", dialCode: "+995", isoCode: "GE", icon: IconGeorgia },
  { name: "Germany", dialCode: "+49", isoCode: "DE", icon: IconGermany },
  { name: "Ghana", dialCode: "+233", isoCode: "GH", icon: IconGhana },
  { name: "Gibraltar", dialCode: "+350", isoCode: "GI", icon: IconGibraltar },
  { name: "Greece", dialCode: "+30", isoCode: "GR", icon: IconGreece },
  { name: "Greenland", dialCode: "+299", isoCode: "GL", icon: IconGreenland },
  { name: "Grenada", dialCode: "+1473", isoCode: "GD", icon: IconGrenada },
  { name: "Guam", dialCode: "+1671", isoCode: "GU", icon: IconGuam },
  { name: "Guatemala", dialCode: "+502", isoCode: "GT", icon: IconGuatemala },
  { name: "Guinea", dialCode: "+224", isoCode: "GN", icon: IconGuinea },
  { name: "Guinea-Bissau", dialCode: "+245", isoCode: "GW", icon: IconGuineaBissau },
  { name: "Guyana", dialCode: "+592", isoCode: "GY", icon: IconGuyana },
  { name: "Haiti", dialCode: "+509", isoCode: "HT", icon: IconHaiti },
  { name: "Honduras", dialCode: "+504", isoCode: "HN", icon: IconHonduras },
  { name: "Hong Kong", dialCode: "+852", isoCode: "HK", icon: IconHongKong },
  { name: "Hungary", dialCode: "+36", isoCode: "HU", icon: IconHungary },
  { name: "Iceland", dialCode: "+354", isoCode: "IS", icon: IconIceland },
  { name: "India", dialCode: "+91", isoCode: "IN", icon: IconIndia },
  { name: "Indonesia", dialCode: "+62", isoCode: "ID", icon: IconIndonesia },
  { name: "Iran", dialCode: "+98", isoCode: "IR", icon: IconIran },
  { name: "Iraq", dialCode: "+964", isoCode: "IQ", icon: IconIraq },
  { name: "Ireland", dialCode: "+353", isoCode: "IE", icon: IconIreland },
  { name: "Israel", dialCode: "+972", isoCode: "IL", icon: IconIsrael },
  { name: "Italy", dialCode: "+39", isoCode: "IT", icon: IconItaly },
  // { name: "Ivory Coast", dialCode: "+225", isoCode: "CI", icon: IconIvoryCoast },
  { name: "Jamaica", dialCode: "+1876", isoCode: "JM", icon: IconJamaica },
  { name: "Japan", dialCode: "+81", isoCode: "JP", icon: IconJapan },
  { name: "Jordan", dialCode: "+962", isoCode: "JO", icon: IconJordan },
  { name: "Kazakhstan", dialCode: "+7", isoCode: "KZ", icon: IconKazakhstan },
  { name: "Kenya", dialCode: "+254", isoCode: "KE", icon: IconKenya },
  { name: "Kiribati", dialCode: "+686", isoCode: "KI", icon: IconKiribati },
  { name: "Kosovo", dialCode: "+383", isoCode: "XK", icon: IconKosovo },
  { name: "Kuwait", dialCode: "+965", isoCode: "KW", icon: IconKuwait },
  { name: "Kyrgyzstan", dialCode: "+996", isoCode: "KG", icon: IconKyrgyzstan },
  { name: "Laos", dialCode: "+856", isoCode: "LA", icon: IconLaos },
  { name: "Latvia", dialCode: "+371", isoCode: "LV", icon: IconLatvia },
  { name: "Lebanon", dialCode: "+961", isoCode: "LB", icon: IconLebanon },
  { name: "Lesotho", dialCode: "+266", isoCode: "LS", icon: IconLesotho },
  { name: "Liberia", dialCode: "+231", isoCode: "LR", icon: IconLiberia },
  { name: "Libya", dialCode: "+218", isoCode: "LY", icon: IconLibya },
  { name: "Liechtenstein", dialCode: "+423", isoCode: "LI", icon: IconLiechtenstein },
  { name: "Lithuania", dialCode: "+370", isoCode: "LT", icon: IconLithuania },
  { name: "Luxembourg", dialCode: "+352", isoCode: "LU", icon: IconLuxembourg },
  { name: "Macao", dialCode: "+853", isoCode: "MO", icon: IconMacao },
  { name: "Macedonia", dialCode: "+389", isoCode: "MK", icon: IconMacedonia },
  { name: "Madagascar", dialCode: "+261", isoCode: "MG", icon: IconMadagascar },
  { name: "Malawi", dialCode: "+265", isoCode: "MW", icon: IconMalawi },
  { name: "Malaysia", dialCode: "+60", isoCode: "MY", icon: IconMalaysia },
  { name: "Maldives", dialCode: "+960", isoCode: "MV", icon: IconMaldives },
  { name: "Mali", dialCode: "+223", isoCode: "ML", icon: IconMali },
  { name: "Malta", dialCode: "+356", isoCode: "MT", icon: IconMalta },
  { name: "Marshall Islands", dialCode: "+692", isoCode: "MH", icon: IconMarshallIslands },
  { name: "Mauritania", dialCode: "+222", isoCode: "MR", icon: IconMauritania },
  { name: "Mauritius", dialCode: "+230", isoCode: "MU", icon: IconMauritius },
  { name: "Mayotte", dialCode: "+262", isoCode: "YT", icon: IconMayotte },
  { name: "Mexico", dialCode: "+52", isoCode: "MX", icon: IconMexico },
  { name: "Micronesia", dialCode: "+691", isoCode: "FM", icon: IconMicronesia },
  { name: "Moldova", dialCode: "+373", isoCode: "MD", icon: IconMoldova },
  { name: "Monaco", dialCode: "+377", isoCode: "MC", icon: IconMonaco },
  { name: "Mongolia", dialCode: "+976", isoCode: "MN", icon: IconMongolia },
  { name: "Montenegro", dialCode: "+382", isoCode: "ME", icon: IconMontenegro },
  { name: "Morocco", dialCode: "+212", isoCode: "MA", icon: IconMorocco },
  { name: "Mozambique", dialCode: "+258", isoCode: "MZ", icon: IconMozambique },
  { name: "Myanmar", dialCode: "+95", isoCode: "MM", icon: IconMyanmar },
  { name: "Namibia", dialCode: "+264", isoCode: "NA", icon: IconNamibia },
  { name: "Nauru", dialCode: "+674", isoCode: "NR", icon: IconNauru },
  { name: "Nepal", dialCode: "+977", isoCode: "NP", icon: IconNepal },
  { name: "Netherlands", dialCode: "+31", isoCode: "NL", icon: IconNetherlands },
  { name: "New Caledonia", dialCode: "+687", isoCode: "NC", icon: IconNewCaledonia },
  { name: "New Zealand", dialCode: "+64", isoCode: "NZ", icon: IconNewZealand },
  { name: "Nicaragua", dialCode: "+505", isoCode: "NI", icon: IconNicaragua },
  { name: "Niger", dialCode: "+227", isoCode: "NE", icon: IconNiger },
  { name: "Nigeria", dialCode: "+234", isoCode: "NG", icon: IconNigeria },
  { name: "Niue", dialCode: "+683", isoCode: "NU", icon: IconNiue },
  { name: "North Korea", dialCode: "+850", isoCode: "KP", icon: IconNorthKorea },
  { name: "Northern Mariana Islands", dialCode: "+1670", isoCode: "MP", icon: IconNorthernMarianaIslands },
  { name: "Norway", dialCode: "+47", isoCode: "NO", icon: IconNorway },
  { name: "Oman", dialCode: "+968", isoCode: "OM", icon: IconOman },
  { name: "Pakistan", dialCode: "+92", isoCode: "PK", icon: IconPakistan },
  { name: "Palau", dialCode: "+680", isoCode: "PW", icon: IconPalau },
  { name: "Palestine", dialCode: "+970", isoCode: "PS", icon: IconPalestine },
  { name: "Panama", dialCode: "+507", isoCode: "PA", icon: IconPanama },
  { name: "Papua New Guinea", dialCode: "+675", isoCode: "PG", icon: IconPapuaNewGuinea },
  { name: "Paraguay", dialCode: "+595", isoCode: "PY", icon: IconParaguay },
  { name: "Peru", dialCode: "+51", isoCode: "PE", icon: IconPeru },
  { name: "Philippines", dialCode: "+63", isoCode: "PH", icon: IconPhilippines },
  { name: "Poland", dialCode: "+48", isoCode: "PL", icon: IconPoland },
  { name: "Portugal", dialCode: "+351", isoCode: "PT", icon: IconPortugal },
  { name: "Puerto Rico", dialCode: "+1939", isoCode: "PR", icon: IconPuertoRico },
  { name: "Qatar", dialCode: "+974", isoCode: "QA", icon: IconQatar },
  { name: "Republic of the Congo", dialCode: "+242", isoCode: "CG", icon: IconRepublicOfTheCongo },
  { name: "Romania", dialCode: "+40", isoCode: "RO", icon: IconRomania },
  { name: "Russia", dialCode: "+7", isoCode: "RU", icon: IconRussia },
  { name: "Rwanda", dialCode: "+250", isoCode: "RW", icon: IconRwanda },
  { name: "Saint Helena", dialCode: "+290", isoCode: "SH", icon: IconSaintHelena },
  { name: "Saint Kitts and Nevis", dialCode: "+1869", isoCode: "KN", icon: IconSaintKittsAndNevis },
  { name: "Saint Lucia", dialCode: "+1758", isoCode: "LC", icon: IconSaintLucia },
  { name: "Saint Pierre and Miquelon", dialCode: "+508", isoCode: "PM", icon: IconSaintPierreAndMiquelon },
  { name: "Saint Vincent and the Grenadines", dialCode: "+1784", isoCode: "VC", icon: IconSaintVincentAndTheGrenadines },
  { name: "Samoa", dialCode: "+685", isoCode: "WS", icon: IconSamoa },
  { name: "San Marino", dialCode: "+378", isoCode: "SM", icon: IconSanMarino },
  { name: "Sao Tome and Principe", dialCode: "+239", isoCode: "ST", icon: IconSaoTomeAndPrincipe },
  { name: "Saudi Arabia", dialCode: "+966", isoCode: "SA", icon: IconSaudiArabia },
  { name: "Senegal", dialCode: "+221", isoCode: "SN", icon: IconSenegal },
  { name: "Serbia", dialCode: "+381", isoCode: "RS", icon: IconSerbia },
  { name: "Seychelles", dialCode: "+248", isoCode: "SC", icon: IconSeychelles },
  { name: "Sierra Leone", dialCode: "+232", isoCode: "SL", icon: IconSierraLeone },
  { name: "Singapore", dialCode: "+65", isoCode: "SG", icon: IconSingapore },
  { name: "Sint Maarten", dialCode: "+1721", isoCode: "SX", icon: IconSintMaarten },
  { name: "Slovakia", dialCode: "+421", isoCode: "SK", icon: IconSlovakia },
  { name: "Slovenia", dialCode: "+386", isoCode: "SI", icon: IconSlovenia },
  { name: "Solomon Islands", dialCode: "+677", isoCode: "SB", icon: IconSolomonIslands },
  { name: "Somalia", dialCode: "+252", isoCode: "SO", icon: IconSomalia },
  { name: "South Africa", dialCode: "+27", isoCode: "ZA", icon: IconSouthAfrica },
  { name: "South Korea", dialCode: "+82", isoCode: "KR", icon: IconSouthKorea },
  { name: "South Sudan", dialCode: "+211", isoCode: "SS", icon: IconSouthSudan },
  { name: "Spain", dialCode: "+34", isoCode: "ES", icon: IconSpain },
  { name: "Sri Lanka", dialCode: "+94", isoCode: "LK", icon: IconSriLanka },
  { name: "Sudan", dialCode: "+249", isoCode: "SD", icon: IconSudan },
  { name: "Suriname", dialCode: "+597", isoCode: "SR", icon: IconSuriname },
  { name: "Eswatini", dialCode: "+268", isoCode: "SZ", icon: IconEswatini },
  { name: "Sweden", dialCode: "+46", isoCode: "SE", icon: IconSweden },
  { name: "Switzerland", dialCode: "+41", isoCode: "CH", icon: IconSwitzerland },
  { name: "Syria", dialCode: "+963", isoCode: "SY", icon: IconSyria },
  { name: "Taiwan", dialCode: "+886", isoCode: "TW", icon: IconTaiwan },
  { name: "Tajikistan", dialCode: "+992", isoCode: "TJ", icon: IconTajikistan },
  { name: "Tanzania", dialCode: "+255", isoCode: "TZ", icon: IconTanzania },
  { name: "Thailand", dialCode: "+66", isoCode: "TH", icon: IconThailand },
  { name: "Togo", dialCode: "+228", isoCode: "TG", icon: IconTogo },
  { name: "Tokelau", dialCode: "+690", isoCode: "TK", icon: IconTokelau },
  { name: "Tonga", dialCode: "+676", isoCode: "TO", icon: IconTonga },
  { name: "Trinidad and Tobago", dialCode: "+1868", isoCode: "TT", icon: IconTrinidadAndTobago },
  { name: "Tunisia", dialCode: "+216", isoCode: "TN", icon: IconTunisia },
  { name: "Turkey", dialCode: "+90", isoCode: "TR", icon: IconTurkey },
  { name: "Turkmenistan", dialCode: "+993", isoCode: "TM", icon: IconTurkmenistan },
  { name: "Turks and Caicos Islands", dialCode: "+1649", isoCode: "TC", icon: IconTurksAndCaicosIslands },
  { name: "Tuvalu", dialCode: "+688", isoCode: "TV", icon: IconTuvalu },
  { name: "Uganda", dialCode: "+256", isoCode: "UG", icon: IconUganda },
  { name: "Ukraine", dialCode: "+380", isoCode: "UA", icon: IconUkraine },
  { name: "United Arab Emirates", dialCode: "+971", isoCode: "AE", icon: IconUnitedArabEmirates },
  { name: "United Kingdom", dialCode: "+44", isoCode: "GB", icon: IconUnitedKingdom },
  { name: "United States", dialCode: "+1", isoCode: "US", icon: IconUnitedStates },
  { name: "Uruguay", dialCode: "+598", isoCode: "UY", icon: IconUruguay },
  { name: "Uzbekistan", dialCode: "+998", isoCode: "UZ", icon: IconUzbekistan },
  { name: "Vanuatu", dialCode: "+678", isoCode: "VU", icon: IconVanuatu },
  { name: "Vatican", dialCode: "+379", isoCode: "VA", icon: IconVatican },
  { name: "Venezuela", dialCode: "+58", isoCode: "VE", icon: IconVenezuela },
  { name: "Vietnam", dialCode: "+84", isoCode: "VN", icon: IconVietnam },
  { name: "Wallis and Futuna", dialCode: "+681", isoCode: "WF", icon: IconWallisAndFutuna },
  { name: "Western Sahara", dialCode: "+212", isoCode: "EH", icon: IconWesternSahara },
  { name: "Yemen", dialCode: "+967", isoCode: "YE", icon: IconYemen },
  { name: "Zambia", dialCode: "+260", isoCode: "ZM", icon: IconZambia },
  { name: "Zimbabwe", dialCode: "+263", isoCode: "ZW", icon: IconZimbabwe },
].sort((a, b) => Number(a.dialCode.slice(1)) - Number(b.dialCode.slice(1)))
