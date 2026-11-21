"""
Test script and visual asset selection with numbering 1..N in 16:9.
Demonstrates clean visual matching, safety filtering, and zero blurred margins.
"""
import sys
from pathlib import Path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from agents.social_visual_selector import select_visuals_for_script
from utils.season_guard import resolve_effective_show_context

roast_script = """బిగ్ బాస్ హౌస్‌లో ఎలిమినేషన్స్ అంటే మామూలు రచ్చ కాదు, కానీ ఈ వారం స్వేతా నాయుడు ఎగ్జిట్ చూస్తే ఎవరికైనా నవ్వాగదు!
నాగార్జున గారు 'స్వేతా, యు ఆర్ ఎలిమినేటెడ్' అని చెప్పగానే హౌస్‌లో మొదలైంది అసలైన ఆస్కార్ లెవల్ డ్రామా!
ఎలిమినేట్ అయినప్పుడు స్వేతా నాయుడు ఇచ్చిన ఎక్స్‌ప్రెషన్స్ చూసి తోటి కంటెస్టెంట్స్‌కే మైండ్ బ్లాంక్ అయిపోయింది!
ఆ ఎమోషనల్ సీన్ చూసి ఆడియన్స్ ఏడవాల్నా లేక నవ్వాల్నా అర్థం కాక తెగ కన్ఫ్యూజ్ అయిపోయారు!
ఢీ డాన్సర్ కదా, ఆ అలవాటు పోక ఎలిమినేషన్ ఎగ్జిట్‌లో కూడా స్టెప్పులు వేస్తూ బయటకు రావడం వేరే లెవల్!
సోషల్ మీడియాలో నెటిజన్లు అయితే 'ఇది ఎలిమినేషనా లేక ఫేర్‌వెల్ పెర్ఫార్మెన్సా?' అని మీమ్స్‌తో ఏకిపారేస్తున్నారు!
హౌస్‌లో అంతసేపు పోరాడి, చివరికి ఇలా కామెడీ ఎగ్జిట్ ఇవ్వడం స్వేతా నాయుడుకే చెల్లింది!
కన్నీళ్ల డ్రామా కాస్తా కాస్తా ట్రోలర్ల చేతిలో పడి ప్యూర్ ఎంటర్‌టైన్‌మెంట్ కామెడీగా మారిపోయింది!
హోస్ట్ నాగార్జున గారు కూడా ఆ ఎగ్జిట్ డ్రామా చూసి నవ్వు ఆపుకోవడం కష్టమైపోయిందంటే పరిస్థితి అర్థం చేసుకోండి!
మరి స్వేతా నాయుడు ఎగ్జిట్ డ్రామాపై మీ కామెంట్ ఏంటో కింద చెప్పండి, మరిన్ని బిగ్ బాస్ రోస్టింగ్ కోసం సబ్‌స్క్రైబ్ చేసుకోండి!"""

print("="*60)
print("TESTING 16:9 VISUAL ASSET SELECTION & MAPPING")
print("="*60)

results = select_visuals_for_script(
    script_text=roast_script.strip(),
    overall_context="Bigg Boss Telugu 10 Swetha Naidu Roast",
    aspect_ratio="16:9"
)

print("\n" + "="*60)
print(f"SUCCESS: Generated {len(results)} Scene Visuals:")
print("="*60)
for idx, p in results:
    from PIL import Image
    im = Image.open(p)
    print(f"Scene {idx:02d} -> {p.name} | Size: {im.size} (Expected 1920x1080) | File: {p}")
