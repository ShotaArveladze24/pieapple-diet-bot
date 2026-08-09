"""Bot interface strings. All notification/UI text is English regardless of the
source PDF's language, which only affects extracted dish names/ingredients."""

MEAL_TYPE_LABELS = {
    "breakfast": "Breakfast",
    "lunch": "Lunch",
    "dinner": "Dinner",
}

STRINGS = {
    "confirm_button": "Confirm",
    "recipe_button": "Recipe",
    "substitute_button": "I don't like it / Substitute",
    "nutrition_button": "Nutrition facts",
    "plan_saved": "Plan saved.",
    "no_meals_today": "No meals planned for today.",
}


def meal_type_label(meal_type: str, language: str = "en") -> str:
    return MEAL_TYPE_LABELS[meal_type]


def t(key: str, language: str = "en") -> str:
    return STRINGS[key]
