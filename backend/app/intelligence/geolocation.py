"""Location extraction with explicit precision.

The previous implementation assigned a country's geographic centre to every
event, which rendered as a precise pin in the middle of the country. Coordinates
are now only stored when the location is actually known to that precision:

``exact``        coordinates supplied by a structured source (USGS, CAP polygon)
``city``         a named city was resolved to coordinates
``admin_region`` a named province/state was resolved
``country``      only the country is known -> no coordinates are stored
``approximate``  the source itself said "near"/"around" a place
``unknown``      nothing could be established

Country centroids are still used internally for *display* hints (e.g. drawing a
country-level marker), but the API always reports ``location_precision`` so the
UI can draw an area rather than a fake pin.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PRECISION_ORDER = ["exact", "city", "admin_region", "country", "approximate", "unknown"]

# Country registry: ISO2, label, centroid (display/anchor only), and aliases.
# The centroid is *never* stored on an event as an observed coordinate.
COUNTRIES: list[dict] = [
    {"code": "AF", "name": "Afghanistan", "lat": 33.9391, "lon": 67.7100, "aliases": ["kabul"]},
    {"code": "AL", "name": "Albania", "lat": 41.1533, "lon": 20.1683, "aliases": ["tirana"]},
    {"code": "DZ", "name": "Algeria", "lat": 28.0339, "lon": 1.6596, "aliases": ["algiers"]},
    {"code": "AR", "name": "Argentina", "lat": -38.4161, "lon": -63.6167, "aliases": ["buenos aires"]},
    {"code": "AM", "name": "Armenia", "lat": 40.0691, "lon": 45.0382, "aliases": ["yerevan"]},
    {"code": "AU", "name": "Australia", "lat": -25.2744, "lon": 133.7751, "aliases": ["sydney", "melbourne", "brisbane", "perth"]},
    {"code": "AT", "name": "Austria", "lat": 47.5162, "lon": 14.5501, "aliases": ["vienna"]},
    {"code": "AZ", "name": "Azerbaijan", "lat": 40.1431, "lon": 47.5769, "aliases": ["baku"]},
    {"code": "BD", "name": "Bangladesh", "lat": 23.6850, "lon": 90.3563, "aliases": ["dhaka", "chittagong"]},
    {"code": "BY", "name": "Belarus", "lat": 53.7098, "lon": 27.9534, "aliases": ["minsk"]},
    {"code": "BE", "name": "Belgium", "lat": 50.5039, "lon": 4.4699, "aliases": ["brussels"]},
    {"code": "BO", "name": "Bolivia", "lat": -16.2902, "lon": -63.5887, "aliases": ["la paz"]},
    {"code": "BA", "name": "Bosnia and Herzegovina", "lat": 43.9159, "lon": 17.6791, "aliases": ["sarajevo"]},
    {"code": "BR", "name": "Brazil", "lat": -14.2350, "lon": -51.9253, "aliases": ["sao paulo", "rio de janeiro", "brasilia"]},
    {"code": "BG", "name": "Bulgaria", "lat": 42.7339, "lon": 25.4858, "aliases": ["sofia"]},
    {"code": "BF", "name": "Burkina Faso", "lat": 12.2383, "lon": -1.5616, "aliases": ["ouagadougou"]},
    {"code": "MM", "name": "Myanmar", "lat": 21.9162, "lon": 95.9560, "aliases": ["yangon", "naypyidaw"]},
    {"code": "BI", "name": "Burundi", "lat": -3.3731, "lon": 29.9189, "aliases": ["bujumbura"]},
    {"code": "KH", "name": "Cambodia", "lat": 12.5657, "lon": 104.9910, "aliases": ["phnom penh"]},
    {"code": "CM", "name": "Cameroon", "lat": 7.3697, "lon": 12.3547, "aliases": ["yaounde", "douala"]},
    {"code": "CA", "name": "Canada", "lat": 56.1304, "lon": -106.3468, "aliases": ["toronto", "vancouver", "ottawa", "montreal"]},
    {"code": "TD", "name": "Chad", "lat": 15.4542, "lon": 18.7322, "aliases": ["ndjamena"]},
    {"code": "CL", "name": "Chile", "lat": -35.6751, "lon": -71.5430, "aliases": ["santiago"]},
    {"code": "CN", "name": "China", "lat": 35.8617, "lon": 104.1954, "aliases": ["beijing", "shanghai", "hong kong", "guangzhou"]},
    {"code": "CO", "name": "Colombia", "lat": 4.5709, "lon": -74.2973, "aliases": ["bogota", "medellin"]},
    {"code": "CD", "name": "Democratic Republic of the Congo", "lat": -4.0383, "lon": 21.7587, "aliases": ["kinshasa", "goma"]},
    {"code": "CG", "name": "Republic of the Congo", "lat": -0.2280, "lon": 15.8277, "aliases": ["brazzaville"]},
    {"code": "CR", "name": "Costa Rica", "lat": 9.7489, "lon": -83.7534, "aliases": ["san jose"]},
    {"code": "HR", "name": "Croatia", "lat": 45.1000, "lon": 15.2000, "aliases": ["zagreb"]},
    {"code": "CU", "name": "Cuba", "lat": 21.5218, "lon": -77.7812, "aliases": ["havana"]},
    {"code": "CY", "name": "Cyprus", "lat": 35.1264, "lon": 33.4299, "aliases": ["nicosia"]},
    {"code": "CZ", "name": "Czechia", "lat": 49.8175, "lon": 15.4730, "aliases": ["prague"]},
    {"code": "DK", "name": "Denmark", "lat": 56.2639, "lon": 9.5018, "aliases": ["copenhagen"]},
    {"code": "DO", "name": "Dominican Republic", "lat": 18.7357, "lon": -70.1627, "aliases": ["santo domingo"]},
    {"code": "EC", "name": "Ecuador", "lat": -1.8312, "lon": -78.1834, "aliases": ["quito", "guayaquil"]},
    {"code": "EG", "name": "Egypt", "lat": 26.8206, "lon": 30.8025, "aliases": ["cairo", "alexandria"]},
    {"code": "SV", "name": "El Salvador", "lat": 13.7942, "lon": -88.8965, "aliases": ["san salvador"]},
    {"code": "ET", "name": "Ethiopia", "lat": 9.1450, "lon": 40.4897, "aliases": ["addis ababa", "tigray"]},
    {"code": "FI", "name": "Finland", "lat": 61.9241, "lon": 25.7482, "aliases": ["helsinki"]},
    {"code": "FR", "name": "France", "lat": 46.2276, "lon": 2.2137, "aliases": ["paris", "marseille", "lyon"]},
    {"code": "GE", "name": "Georgia", "lat": 42.3154, "lon": 43.3569, "aliases": ["tbilisi"]},
    {"code": "DE", "name": "Germany", "lat": 51.1657, "lon": 10.4515, "aliases": ["berlin", "munich", "hamburg", "frankfurt"]},
    {"code": "GH", "name": "Ghana", "lat": 7.9465, "lon": -1.0232, "aliases": ["accra"]},
    {"code": "GR", "name": "Greece", "lat": 39.0742, "lon": 21.8243, "aliases": ["athens", "thessaloniki"]},
    {"code": "GT", "name": "Guatemala", "lat": 15.7835, "lon": -90.2308, "aliases": ["guatemala city"]},
    {"code": "HT", "name": "Haiti", "lat": 18.9712, "lon": -72.2852, "aliases": ["port-au-prince"]},
    {"code": "HN", "name": "Honduras", "lat": 15.2000, "lon": -86.2419, "aliases": ["tegucigalpa"]},
    {"code": "HU", "name": "Hungary", "lat": 47.1625, "lon": 19.5033, "aliases": ["budapest"]},
    {"code": "IN", "name": "India", "lat": 20.5937, "lon": 78.9629, "aliases": ["delhi", "new delhi", "mumbai", "kolkata", "chennai", "bengaluru", "kashmir"]},
    {"code": "ID", "name": "Indonesia", "lat": -0.7893, "lon": 113.9213, "aliases": ["jakarta", "surabaya", "bali", "sumatra", "java"]},
    {"code": "IR", "name": "Iran", "lat": 32.4279, "lon": 53.6880, "aliases": ["tehran", "isfahan", "tabriz"]},
    {"code": "IQ", "name": "Iraq", "lat": 33.2232, "lon": 43.6793, "aliases": ["baghdad", "mosul", "basra", "erbil"]},
    {"code": "IE", "name": "Ireland", "lat": 53.4129, "lon": -8.2439, "aliases": ["dublin"]},
    {"code": "IL", "name": "Israel", "lat": 31.0461, "lon": 34.8516, "aliases": ["jerusalem", "tel aviv", "gaza"]},
    {"code": "IT", "name": "Italy", "lat": 41.8719, "lon": 12.5674, "aliases": ["rome", "milan", "naples", "sicily"]},
    {"code": "JM", "name": "Jamaica", "lat": 18.1096, "lon": -77.2975, "aliases": ["kingston"]},
    {"code": "JP", "name": "Japan", "lat": 36.2048, "lon": 138.2529, "aliases": ["tokyo", "osaka", "kyoto", "okinawa", "honshu", "hokkaido"]},
    {"code": "JO", "name": "Jordan", "lat": 30.5852, "lon": 36.2384, "aliases": ["amman"]},
    {"code": "KZ", "name": "Kazakhstan", "lat": 48.0196, "lon": 66.9237, "aliases": ["almaty", "astana"]},
    {"code": "KE", "name": "Kenya", "lat": -0.0236, "lon": 37.9062, "aliases": ["nairobi", "mombasa"]},
    {"code": "KP", "name": "North Korea", "lat": 40.3399, "lon": 127.5101, "aliases": ["pyongyang"]},
    {"code": "KR", "name": "South Korea", "lat": 35.9078, "lon": 127.7669, "aliases": ["seoul", "busan"]},
    {"code": "KW", "name": "Kuwait", "lat": 29.3117, "lon": 47.4818, "aliases": ["kuwait city"]},
    {"code": "KG", "name": "Kyrgyzstan", "lat": 41.2044, "lon": 74.7661, "aliases": ["bishkek"]},
    {"code": "LA", "name": "Laos", "lat": 19.8563, "lon": 102.4955, "aliases": ["vientiane"]},
    {"code": "LV", "name": "Latvia", "lat": 56.8796, "lon": 24.6032, "aliases": ["riga"]},
    {"code": "LB", "name": "Lebanon", "lat": 33.8547, "lon": 35.8623, "aliases": ["beirut"]},
    {"code": "LY", "name": "Libya", "lat": 26.3351, "lon": 17.2283, "aliases": ["tripoli", "benghazi"]},
    {"code": "LT", "name": "Lithuania", "lat": 55.1694, "lon": 23.8813, "aliases": ["vilnius"]},
    {"code": "MY", "name": "Malaysia", "lat": 4.2105, "lon": 101.9758, "aliases": ["kuala lumpur", "penang"]},
    {"code": "ML", "name": "Mali", "lat": 17.5707, "lon": -3.9962, "aliases": ["bamako", "timbuktu"]},
    {"code": "MT", "name": "Malta", "lat": 35.9375, "lon": 14.3754, "aliases": ["valletta"]},
    {"code": "MX", "name": "Mexico", "lat": 23.6345, "lon": -102.5528, "aliases": ["mexico city", "guadalajara", "monterrey"]},
    {"code": "MD", "name": "Moldova", "lat": 47.4116, "lon": 28.3699, "aliases": ["chisinau"]},
    {"code": "MN", "name": "Mongolia", "lat": 46.8625, "lon": 103.8467, "aliases": ["ulaanbaatar"]},
    {"code": "MA", "name": "Morocco", "lat": 31.7917, "lon": -7.0926, "aliases": ["rabat", "casablanca", "marrakesh"]},
    {"code": "MZ", "name": "Mozambique", "lat": -18.6657, "lon": 35.5296, "aliases": ["maputo", "cabo delgado"]},
    {"code": "NP", "name": "Nepal", "lat": 28.3949, "lon": 84.1240, "aliases": ["kathmandu"]},
    {"code": "NL", "name": "Netherlands", "lat": 52.1326, "lon": 5.2913, "aliases": ["amsterdam", "the hague", "rotterdam"]},
    {"code": "NZ", "name": "New Zealand", "lat": -40.9006, "lon": 174.8860, "aliases": ["auckland", "wellington", "christchurch"]},
    {"code": "NI", "name": "Nicaragua", "lat": 12.8654, "lon": -85.2072, "aliases": ["managua"]},
    {"code": "NE", "name": "Niger", "lat": 17.6078, "lon": 8.0817, "aliases": ["niamey"]},
    {"code": "NG", "name": "Nigeria", "lat": 9.0820, "lon": 8.6753, "aliases": ["lagos", "abuja", "kano"]},
    {"code": "NO", "name": "Norway", "lat": 60.4720, "lon": 8.4689, "aliases": ["oslo"]},
    {"code": "OM", "name": "Oman", "lat": 21.4735, "lon": 55.9754, "aliases": ["muscat"]},
    {"code": "PK", "name": "Pakistan", "lat": 30.3753, "lon": 69.3451, "aliases": ["islamabad", "karachi", "lahore", "peshawar", "balochistan"]},
    {"code": "PS", "name": "Palestine", "lat": 31.9522, "lon": 35.2332, "aliases": ["gaza", "west bank", "ramallah"]},
    {"code": "PA", "name": "Panama", "lat": 8.5380, "lon": -80.7821, "aliases": ["panama city"]},
    {"code": "PY", "name": "Paraguay", "lat": -23.4425, "lon": -58.4438, "aliases": ["asuncion"]},
    {"code": "PE", "name": "Peru", "lat": -9.1900, "lon": -75.0152, "aliases": ["lima"]},
    {"code": "PH", "name": "Philippines", "lat": 12.8797, "lon": 121.7740, "aliases": ["manila", "cebu", "mindanao", "luzon"]},
    {"code": "PL", "name": "Poland", "lat": 51.9194, "lon": 19.1451, "aliases": ["warsaw", "krakow"]},
    {"code": "PT", "name": "Portugal", "lat": 39.3999, "lon": -8.2245, "aliases": ["lisbon", "porto"]},
    {"code": "QA", "name": "Qatar", "lat": 25.3548, "lon": 51.1839, "aliases": ["doha"]},
    {"code": "RO", "name": "Romania", "lat": 45.9432, "lon": 24.9668, "aliases": ["bucharest"]},
    {"code": "RU", "name": "Russia", "lat": 61.5240, "lon": 105.3188, "aliases": ["moscow", "st petersburg", "kursk", "siberia"]},
    {"code": "RW", "name": "Rwanda", "lat": -1.9403, "lon": 29.8739, "aliases": ["kigali"]},
    {"code": "SA", "name": "Saudi Arabia", "lat": 23.8859, "lon": 45.0792, "aliases": ["riyadh", "jeddah"]},
    {"code": "SN", "name": "Senegal", "lat": 14.4974, "lon": -14.4524, "aliases": ["dakar"]},
    {"code": "RS", "name": "Serbia", "lat": 44.0165, "lon": 21.0059, "aliases": ["belgrade"]},
    {"code": "SL", "name": "Sierra Leone", "lat": 8.4606, "lon": -11.7799, "aliases": ["freetown"]},
    {"code": "SG", "name": "Singapore", "lat": 1.3521, "lon": 103.8198, "aliases": []},
    {"code": "SK", "name": "Slovakia", "lat": 48.6690, "lon": 19.6990, "aliases": ["bratislava"]},
    {"code": "SI", "name": "Slovenia", "lat": 46.1512, "lon": 14.9955, "aliases": ["ljubljana"]},
    {"code": "SO", "name": "Somalia", "lat": 5.1521, "lon": 46.1996, "aliases": ["mogadishu"]},
    {"code": "ZA", "name": "South Africa", "lat": -30.5595, "lon": 22.9375, "aliases": ["johannesburg", "cape town", "durban"]},
    {"code": "SS", "name": "South Sudan", "lat": 6.8770, "lon": 31.3070, "aliases": ["juba"]},
    {"code": "ES", "name": "Spain", "lat": 40.4637, "lon": -3.7492, "aliases": ["madrid", "barcelona", "valencia"]},
    {"code": "LK", "name": "Sri Lanka", "lat": 7.8731, "lon": 80.7718, "aliases": ["colombo", "kandy", "galle", "jaffna"]},
    {"code": "SD", "name": "Sudan", "lat": 12.8628, "lon": 30.2176, "aliases": ["khartoum", "darfur", "omdurman"]},
    {"code": "SE", "name": "Sweden", "lat": 60.1282, "lon": 18.6435, "aliases": ["stockholm"]},
    {"code": "CH", "name": "Switzerland", "lat": 46.8182, "lon": 8.2275, "aliases": ["geneva", "zurich", "bern"]},
    {"code": "SY", "name": "Syria", "lat": 34.8021, "lon": 38.9968, "aliases": ["damascus", "aleppo", "idlib"]},
    {"code": "TW", "name": "Taiwan", "lat": 23.6978, "lon": 120.9605, "aliases": ["taipei"]},
    {"code": "TJ", "name": "Tajikistan", "lat": 38.8610, "lon": 71.2761, "aliases": ["dushanbe"]},
    {"code": "TZ", "name": "Tanzania", "lat": -6.3690, "lon": 34.8888, "aliases": ["dar es salaam"]},
    {"code": "TH", "name": "Thailand", "lat": 15.8700, "lon": 100.9925, "aliases": ["bangkok", "phuket"]},
    {"code": "TN", "name": "Tunisia", "lat": 33.8869, "lon": 9.5375, "aliases": ["tunis"]},
    {"code": "TR", "name": "Turkey", "lat": 38.9637, "lon": 35.2433, "aliases": ["ankara", "istanbul", "izmir"]},
    {"code": "TM", "name": "Turkmenistan", "lat": 38.9697, "lon": 59.5563, "aliases": ["ashgabat"]},
    {"code": "UG", "name": "Uganda", "lat": 1.3733, "lon": 32.2903, "aliases": ["kampala"]},
    {"code": "UA", "name": "Ukraine", "lat": 48.3794, "lon": 31.1656, "aliases": ["kyiv", "kiev", "kharkiv", "odesa", "odessa", "donetsk", "mariupol", "zaporizhzhia"]},
    {"code": "AE", "name": "United Arab Emirates", "lat": 23.4241, "lon": 53.8478, "aliases": ["dubai", "abu dhabi"]},
    {"code": "GB", "name": "United Kingdom", "lat": 55.3781, "lon": -3.4360, "aliases": ["london", "manchester", "birmingham", "scotland", "wales", "england", "northern ireland"]},
    {"code": "US", "name": "United States", "lat": 37.0902, "lon": -95.7129, "aliases": ["washington", "new york", "los angeles", "chicago", "california", "texas", "florida"]},
    {"code": "UY", "name": "Uruguay", "lat": -32.5228, "lon": -55.7658, "aliases": ["montevideo"]},
    {"code": "UZ", "name": "Uzbekistan", "lat": 41.3775, "lon": 64.5853, "aliases": ["tashkent"]},
    {"code": "VE", "name": "Venezuela", "lat": 6.4238, "lon": -66.5897, "aliases": ["caracas"]},
    {"code": "VN", "name": "Vietnam", "lat": 14.0583, "lon": 108.2772, "aliases": ["hanoi", "ho chi minh"]},
    {"code": "YE", "name": "Yemen", "lat": 15.5527, "lon": 48.5164, "aliases": ["sanaa", "aden", "hodeidah"]},
    {"code": "ZM", "name": "Zambia", "lat": -13.1339, "lon": 27.8493, "aliases": ["lusaka"]},
    {"code": "ZW", "name": "Zimbabwe", "lat": -19.0154, "lon": 29.1549, "aliases": ["harare"]},
]

COUNTRY_BY_CODE = {c["code"]: c for c in COUNTRIES}
COUNTRY_BY_NAME = {c["name"].lower(): c for c in COUNTRIES}

# Additional country-name spellings seen in headlines.
NAME_ALIASES = {
    "usa": "US", "u.s.": "US", "united states of america": "US", "america": "US",
    "uk": "GB", "britain": "GB", "great britain": "GB", "england": "GB",
    "scotland": "GB", "wales": "GB", "northern ireland": "GB",
    "south korea": "KR", "north korea": "KP", "dprk": "KP", "korea": "KR",
    "russia": "RU", "russian federation": "RU",
    "ivory coast": "CI", "cote d'ivoire": "CI",
    "czech republic": "CZ", "burma": "MM", "holland": "NL",
    "the gambia": "GM", "cape verde": "CV", "swaziland": "SZ", "eswatini": "SZ",
    "turkiye": "TR", "vatican": "VA", "uae": "AE", "emirates": "AE",
    "congo": "CG", "drc": "CD", "dr congo": "CD",
}

# City -> (lat, lon, admin region name). Used to promote country-level events to
# city-level when the article names a place we can actually locate.
CITIES: dict[str, tuple[float, float, str, str]] = {
    "tokyo": (35.6762, 139.6503, "Tokyo", "JP"),
    "osaka": (34.6937, 135.5023, "Osaka", "JP"),
    "kyoto": (35.0116, 135.7681, "Kyoto", "JP"),
    "beijing": (39.9042, 116.4074, "Beijing", "CN"),
    "shanghai": (31.2304, 121.4737, "Shanghai", "CN"),
    "hong kong": (22.3193, 114.1694, "Hong Kong", "CN"),
    "delhi": (28.6139, 77.2090, "Delhi", "IN"),
    "new delhi": (28.6139, 77.2090, "Delhi", "IN"),
    "mumbai": (19.0760, 72.8777, "Maharashtra", "IN"),
    "kolkata": (22.5726, 88.3639, "West Bengal", "IN"),
    "chennai": (13.0827, 80.2707, "Tamil Nadu", "IN"),
    "bengaluru": (12.9716, 77.5946, "Karnataka", "IN"),
    "karachi": (24.8607, 67.0011, "Sindh", "PK"),
    "lahore": (31.5204, 74.3587, "Punjab", "PK"),
    "islamabad": (33.6844, 73.0479, "Islamabad", "PK"),
    "dhaka": (23.8103, 90.4125, "Dhaka", "BD"),
    "colombo": (6.9271, 79.8612, "Western Province", "LK"),
    "kandy": (7.2906, 80.6337, "Central Province", "LK"),
    "jakarta": (-6.2088, 106.8456, "Jakarta", "ID"),
    "manila": (14.5995, 120.9842, "Metro Manila", "PH"),
    "bangkok": (13.7563, 100.5018, "Bangkok", "TH"),
    "hanoi": (21.0278, 105.8342, "Hanoi", "VN"),
    "kuala lumpur": (3.1390, 101.6869, "Kuala Lumpur", "MY"),
    "singapore": (1.3521, 103.8198, "Singapore", "SG"),
    "sydney": (-33.8688, 151.2093, "New South Wales", "AU"),
    "melbourne": (-37.8136, 144.9631, "Victoria", "AU"),
    "auckland": (-36.8485, 174.7633, "Auckland", "NZ"),
    "washington": (38.9072, -77.0369, "District of Columbia", "US"),
    "new york": (40.7128, -74.0060, "New York", "US"),
    "los angeles": (34.0522, -118.2437, "California", "US"),
    "chicago": (41.8781, -87.6298, "Illinois", "US"),
    "houston": (29.7604, -95.3698, "Texas", "US"),
    "miami": (25.7617, -80.1918, "Florida", "US"),
    "toronto": (43.6532, -79.3832, "Ontario", "CA"),
    "vancouver": (49.2827, -123.1207, "British Columbia", "CA"),
    "mexico city": (19.4326, -99.1332, "Mexico City", "MX"),
    "bogota": (4.7110, -74.0721, "Bogota", "CO"),
    "lima": (-12.0464, -77.0428, "Lima", "PE"),
    "santiago": (-33.4489, -70.6693, "Santiago Metropolitan", "CL"),
    "buenos aires": (-34.6037, -58.3816, "Buenos Aires", "AR"),
    "sao paulo": (-23.5505, -46.6333, "Sao Paulo", "BR"),
    "rio de janeiro": (-22.9068, -43.1729, "Rio de Janeiro", "BR"),
    "london": (51.5074, -0.1278, "England", "GB"),
    "manchester": (53.4808, -2.2426, "England", "GB"),
    "birmingham": (52.4862, -1.8904, "England", "GB"),
    "dublin": (53.3498, -6.2603, "Leinster", "IE"),
    "paris": (48.8566, 2.3522, "Ile-de-France", "FR"),
    "marseille": (43.2965, 5.3698, "Provence-Alpes-Cote d'Azur", "FR"),
    "berlin": (52.5200, 13.4050, "Berlin", "DE"),
    "munich": (48.1351, 11.5820, "Bavaria", "DE"),
    "hamburg": (53.5511, 9.9937, "Hamburg", "DE"),
    "madrid": (40.4168, -3.7038, "Madrid", "ES"),
    "barcelona": (41.3874, 2.1686, "Catalonia", "ES"),
    "rome": (41.9028, 12.4964, "Lazio", "IT"),
    "milan": (45.4642, 9.1900, "Lombardy", "IT"),
    "athens": (37.9838, 23.7275, "Attica", "GR"),
    "istanbul": (41.0082, 28.9784, "Istanbul", "TR"),
    "ankara": (39.9334, 32.8597, "Ankara", "TR"),
    "moscow": (55.7558, 37.6173, "Moscow", "RU"),
    "kyiv": (50.4501, 30.5234, "Kyiv", "UA"),
    "kiev": (50.4501, 30.5234, "Kyiv", "UA"),
    "kharkiv": (49.9935, 36.2304, "Kharkiv Oblast", "UA"),
    "odesa": (46.4825, 30.7233, "Odesa Oblast", "UA"),
    "odessa": (46.4825, 30.7233, "Odesa Oblast", "UA"),
    "donetsk": (48.0159, 37.8028, "Donetsk Oblast", "UA"),
    "mariupol": (47.0971, 37.5434, "Donetsk Oblast", "UA"),
    "zaporizhzhia": (47.8388, 35.1396, "Zaporizhzhia Oblast", "UA"),
    "gaza": (31.5017, 34.4668, "Gaza Strip", "PS"),
    "jerusalem": (31.7683, 35.2137, "Jerusalem", "IL"),
    "tel aviv": (32.0853, 34.7818, "Tel Aviv", "IL"),
    "beirut": (33.8938, 35.5018, "Beirut", "LB"),
    "damascus": (33.5138, 36.2765, "Damascus", "SY"),
    "aleppo": (36.2021, 37.1343, "Aleppo", "SY"),
    "baghdad": (33.3152, 44.3661, "Baghdad", "IQ"),
    "mosul": (36.3350, 43.1189, "Nineveh", "IQ"),
    "tehran": (35.6892, 51.3890, "Tehran", "IR"),
    "riyadh": (24.7136, 46.6753, "Riyadh", "SA"),
    "dubai": (25.2048, 55.2708, "Dubai", "AE"),
    "doha": (25.2854, 51.5310, "Doha", "QA"),
    "cairo": (30.0444, 31.2357, "Cairo", "EG"),
    "khartoum": (15.5007, 32.5599, "Khartoum", "SD"),
    "darfur": (13.0000, 25.0000, "Darfur", "SD"),
    "addis ababa": (9.0320, 38.7469, "Addis Ababa", "ET"),
    "tigray": (14.0000, 38.5000, "Tigray", "ET"),
    "mogadishu": (2.0469, 45.3182, "Banaadir", "SO"),
    "nairobi": (-1.2921, 36.8219, "Nairobi", "KE"),
    "lagos": (6.5244, 3.3792, "Lagos", "NG"),
    "abuja": (9.0765, 7.3986, "Federal Capital Territory", "NG"),
    "kano": (12.0022, 8.5920, "Kano", "NG"),
    "kinshasa": (-4.4419, 15.2663, "Kinshasa", "CD"),
    "goma": (-1.6585, 29.2205, "North Kivu", "CD"),
    "johannesburg": (-26.2041, 28.0473, "Gauteng", "ZA"),
    "cape town": (-33.9249, 18.4241, "Western Cape", "ZA"),
    "juba": (4.8594, 31.5713, "Central Equatoria", "SS"),
    "port-au-prince": (18.5944, -72.3074, "Ouest", "HT"),
    "caracas": (10.4806, -66.9036, "Capital District", "VE"),
    "havana": (23.1136, -82.3666, "Havana", "CU"),
    "kabul": (34.5553, 69.2075, "Kabul", "AF"),
    "yangon": (16.8409, 96.1735, "Yangon", "MM"),
    "taipei": (25.0330, 121.5654, "Taipei", "TW"),
    "seoul": (37.5665, 126.9780, "Seoul", "KR"),
    "pyongyang": (39.0392, 125.7625, "Pyongyang", "KP"),
    "warsaw": (52.2297, 21.0122, "Masovia", "PL"),
    "prague": (50.0755, 14.4378, "Prague", "CZ"),
    "vienna": (48.2082, 16.3738, "Vienna", "AT"),
    "amsterdam": (52.3676, 4.9041, "North Holland", "NL"),
    "brussels": (50.8503, 4.3517, "Brussels", "BE"),
    "stockholm": (59.3293, 18.0686, "Stockholm", "SE"),
    "oslo": (59.9139, 10.7522, "Oslo", "NO"),
    "helsinki": (60.1699, 24.9384, "Uusimaa", "FI"),
    "geneva": (46.2044, 6.1432, "Geneva", "CH"),
    "lisbon": (38.7223, -9.1393, "Lisbon", "PT"),
    "algiers": (36.7538, 3.0588, "Algiers", "DZ"),
    "tunis": (36.8065, 10.1815, "Tunis", "TN"),
    "tripoli": (32.8872, 13.1913, "Tripoli", "LY"),
    "sanaa": (15.3694, 44.1910, "Sanaa", "YE"),
    "aden": (12.7855, 45.0187, "Aden", "YE"),
}

APPROXIMATE_MARKERS = (
    "near ", "nearby", "around ", "close to", "outskirts", "region of",
    "off the coast", "approximately",
)

UNRESOLVED_LOCATION_MARKERS = ("unknown", "unclear", "unconfirmed", "not specified")


@dataclass
class LocationResult:
    country: str | None = None
    country_code: str | None = None
    city: str | None = None
    admin_region: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    precision: str = "unknown"
    location_text: str | None = None
    source: str = "text_extraction"
    confidence: float = 0.0
    candidates: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "country": self.country,
            "country_code": self.country_code,
            "city": self.city,
            "admin_region": self.admin_region,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "precision": self.precision,
            "location_text": self.location_text,
            "source": self.source,
            "confidence": self.confidence,
        }


def _find_country(text: str) -> dict | None:
    for name, entry in COUNTRY_BY_NAME.items():
        if re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", text):
            return entry
    for alias, code in NAME_ALIASES.items():
        if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", text):
            return COUNTRY_BY_CODE.get(code)
    return None


def _find_city(text: str) -> tuple[str, tuple[float, float, str, str]] | None:
    best = None
    for city, data in CITIES.items():
        if re.search(rf"(?<![a-z]){re.escape(city)}(?![a-z])", text):
            if best is None or len(city) > len(best[0]):
                best = (city, data)
    return best


def is_approximate_context(text: str, index: int) -> bool:
    window = text[max(0, index - 40): index + 40]
    return any(marker in window for marker in APPROXIMATE_MARKERS)


def extract_location(
    text: str,
    *,
    fallback_country: str | None = None,
    fallback_country_code: str | None = None,
) -> LocationResult:
    """Infer location and, crucially, its precision from free text."""
    haystack = " " + re.sub(r"\s+", " ", (text or "").lower()) + " "

    city_match = _find_city(haystack)
    country_entry = _find_country(haystack)

    if city_match:
        city_name, (lat, lon, region, code) = city_match
        index = haystack.find(city_name)
        approximate = is_approximate_context(haystack, index)
        country = COUNTRY_BY_CODE.get(code, {})
        return LocationResult(
            country=country.get("name"),
            country_code=code,
            city=city_name.title() if city_name.islower() else city_name,
            admin_region=region,
            latitude=round(lat, 4) if approximate else lat,
            longitude=round(lon, 4) if approximate else lon,
            precision="approximate" if approximate else "city",
            location_text=city_name.title(),
            source="city_registry",
            confidence=0.7 if approximate else 0.85,
        )

    if country_entry:
        return LocationResult(
            country=country_entry["name"],
            country_code=country_entry["code"],
            latitude=None,  # country centroid is never an observed coordinate
            longitude=None,
            precision="country",
            location_text=country_entry["name"],
            source="country_registry",
            confidence=0.6,
            candidates=[
                {
                    "label": country_entry["name"],
                    "latitude": country_entry["lat"],
                    "longitude": country_entry["lon"],
                    "precision": "country_centroid_hint",
                }
            ],
        )

    if fallback_country or fallback_country_code:
        entry = COUNTRY_BY_CODE.get((fallback_country_code or "").upper()) or COUNTRY_BY_NAME.get(
            (fallback_country or "").lower()
        )
        return LocationResult(
            country=entry["name"] if entry else fallback_country,
            country_code=entry["code"] if entry else (fallback_country_code or None),
            latitude=None,
            longitude=None,
            precision="country",
            location_text=(entry["name"] if entry else fallback_country),
            source="provider_reference",
            confidence=0.55,
        )

    return LocationResult(precision="unknown", source="none", confidence=0.0)


def coordinate_for_country(country_code: str | None) -> tuple[float, float] | None:
    """Display anchor for country-level events (never stored as event lat/lon)."""
    entry = COUNTRY_BY_CODE.get((country_code or "").upper())
    if not entry:
        return None
    return entry["lat"], entry["lon"]


def precision_rank(precision: str | None) -> int:
    try:
        return len(PRECISION_ORDER) - PRECISION_ORDER.index(precision or "unknown")
    except ValueError:
        return 0
