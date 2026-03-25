"""
Fitness plan factory. Generates personalized 12-week training programs.
Core Gumroad product at $17 (basic) / $27 (premium).
Uses Claude to generate the plan, then formats as PDF.
"""
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("outputs/reports")


@dataclass
class FitnessProfile:
    name: str
    gender: str  # male/female
    age: int
    weight_kg: float
    height_cm: float
    goal: str  # muscle_building / fat_loss / strength / endurance
    experience: str  # beginner / intermediate / advanced
    equipment: str  # gym / home / bodyweight_only
    days_per_week: int  # 2-6
    injuries: str = ""
    notes: str = ""


async def generate(profile: FitnessProfile, tier: str = "basic") -> str:
    """
    Generate a personalized fitness plan.

    Args:
        profile: FitnessProfile with user data
        tier: 'basic' ($17) or 'premium' ($27 — adds nutrition + supplement guide)

    Returns:
        Path to generated PDF or Markdown file
    """
    import anthropic
    client = anthropic.AsyncAnthropic()

    bmi = profile.weight_kg / ((profile.height_cm / 100) ** 2)
    tdee_estimate = _estimate_tdee(profile)

    prompt = f"""Create a detailed 12-week personalized fitness program for:

Name: {profile.name}
Gender: {profile.gender}, Age: {profile.age}
Weight: {profile.weight_kg}kg, Height: {profile.height_cm}cm, BMI: {bmi:.1f}
Goal: {profile.goal}
Experience: {profile.experience}
Equipment: {profile.equipment}
Training days/week: {profile.days_per_week}
Injuries/limitations: {profile.injuries or 'None'}
Notes: {profile.notes or 'None'}
Estimated TDEE: {tdee_estimate} calories/day

Generate a complete 12-week program with:
1. Weekly structure (which days to train which muscle groups)
2. Week 1-4 exercises with sets/reps/rest
3. Week 5-8 progression (heavier, more volume)
4. Week 9-12 peak phase
5. Deload week (week 13)
{"6. Nutrition guide (calorie targets, macro split, meal timing)" if tier == "premium" else ""}
{"7. Supplement guide (evidence-based only)" if tier == "premium" else ""}

Format as clean Markdown. Be specific with weights (use % of 1RM or RPE scale).
Include coaching cues for main lifts.
"""

    msg = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    plan_text = msg.content[0].text

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"fitness_plan_{profile.name.lower().replace(' ', '_')}.md"
    output_path = OUTPUT_DIR / filename
    output_path.write_text(f"# Fitness Plan — {profile.name}\n\n{plan_text}", encoding="utf-8")
    logger.info(f"Fitness plan generated: {output_path}")
    return str(output_path)


def _estimate_tdee(profile: FitnessProfile) -> int:
    """Estimate Total Daily Energy Expenditure using Mifflin-St Jeor."""
    if profile.gender.lower() == "male":
        bmr = 10 * profile.weight_kg + 6.25 * profile.height_cm - 5 * profile.age + 5
    else:
        bmr = 10 * profile.weight_kg + 6.25 * profile.height_cm - 5 * profile.age - 161

    activity_multipliers = {1: 1.2, 2: 1.375, 3: 1.375, 4: 1.55, 5: 1.725, 6: 1.9}
    multiplier = activity_multipliers.get(profile.days_per_week, 1.55)
    return int(bmr * multiplier)
