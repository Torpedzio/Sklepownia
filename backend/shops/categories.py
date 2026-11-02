from .choices import Industry

# Starter product categories per industry; the shop owner renames them later.
INDUSTRY_CATEGORIES = {
    Industry.FASHION: ["Sukienki", "Koszule i bluzki", "Spodnie", "Kurtki i płaszcze", "Swetry", "Obuwie",
                       "Torebki", "Akcesoria", "Bielizna", "Odzież sportowa"],
    Industry.ELECTRONICS: ["Smartfony", "Laptopy", "Tablety", "Słuchawki", "Głośniki", "Akcesoria",
                           "Telewizory", "Smartwatche", "Gaming", "Kable i ładowarki"],
    Industry.HOME_GARDEN: ["Meble", "Dekoracje", "Oświetlenie", "Tekstylia", "Kuchnia", "Łazienka",
                           "Ogród", "Narzędzia", "Rośliny", "Przechowywanie"],
    Industry.BEAUTY: ["Pielęgnacja twarzy", "Pielęgnacja ciała", "Makijaż", "Perfumy", "Włosy",
                      "Paznokcie", "Kosmetyki naturalne", "Dla mężczyzn", "Akcesoria", "Zestawy"],
    Industry.FOOD: ["Kawa", "Herbata", "Słodycze", "Przekąski", "Przyprawy", "Oleje i oliwy",
                    "Produkty ekologiczne", "Napoje", "Bakalie", "Zestawy prezentowe"],
    Industry.SPORTS: ["Fitness", "Bieganie", "Rowery", "Sporty zimowe", "Turystyka", "Sporty wodne",
                      "Odzież sportowa", "Obuwie sportowe", "Suplementy", "Akcesoria"],
    Industry.KIDS: ["Zabawki", "Gry", "Ubranka", "Książeczki", "Wózki i foteliki", "Pielęgnacja",
                    "Pokój dziecka", "Zabawki edukacyjne", "Na zewnątrz", "Dla niemowląt"],
    Industry.BOOKS: ["Literatura piękna", "Kryminały", "Fantastyka", "Poradniki", "Dla dzieci",
                     "Biografie", "Nauka", "Komiksy", "Audiobooki", "E-booki"],
    Industry.HANDMADE: ["Biżuteria", "Ceramika", "Dekoracje", "Świece", "Torby i plecaki",
                        "Tekstylia", "Obrazy", "Mydła", "Prezenty", "Zamówienia indywidualne"],
    Industry.AUTOMOTIVE: ["Części", "Akcesoria", "Opony", "Oleje i płyny", "Kosmetyki samochodowe",
                          "Narzędzia", "Elektronika", "Oświetlenie", "Bagażniki", "Motocykle"],
    Industry.PETS: ["Psy", "Koty", "Gryzonie", "Ptaki", "Akwarystyka", "Karma", "Zabawki",
                    "Legowiska", "Pielęgnacja", "Smycze i obroże"],
}


def category_names(industry, count):
    names = INDUSTRY_CATEGORIES.get(industry, [])[:count]
    return names + [f"Kategoria {i}" for i in range(len(names) + 1, count + 1)]
