#!/usr/bin/env python3
"""
Organize Learning & Fitness library by category.
Runs on Windows; scans F:\Plex\Learning and creates subdirectories.
"""

import os
import shutil
import re
from pathlib import Path
from collections import defaultdict

# Categorization rules: (pattern, category, description)
CATEGORIES = [
    # Fitness & Exercise
    (r'(?i)(yoga|pilates|stretching|flexibility)', 'Fitness - Yoga & Stretching', '🧘 Yoga, Pilates, Flexibility'),
    (r'(?i)(gym|weight|strength|workout|cardio|hiit|training)', 'Fitness - Strength & Cardio', '💪 Gym, Weights, HIIT, Cardio'),
    (r'(?i)(dance|zumba|ballet|hip.?hop)', 'Fitness - Dance', '💃 Dance, Zumba, Ballet'),
    (r'(?i)(running|jogging|marathon|5k)', 'Fitness - Running', '🏃 Running, Jogging, Marathon'),
    (r'(?i)(sports|basketball|soccer|tennis|martial.?art|karate|boxing)', 'Fitness - Sports', '⚽ Sports, Martial Arts, Boxing'),
    (r'(?i)(nutrition|diet|cooking|recipe|meal.?prep)', 'Health - Nutrition & Cooking', '🍎 Nutrition, Diets, Cooking'),
    (r'(?i)(meditation|mindfulness|breathing|relaxation)', 'Wellness - Meditation', '🧠 Meditation, Mindfulness'),

    # Academic & Test Prep
    (r'(?i)(gre|sat|act|lsat|mcat)', 'Academics - Standardized Tests', '📝 GRE, SAT, ACT, LSAT, MCAT'),
    (r'(?i)(math|calculus|algebra|geometry|trigonometry|statistics)', 'Academics - Mathematics', '📐 Math, Calculus, Algebra'),
    (r'(?i)(physics|chemistry|biology|science)', 'Academics - Sciences', '🔬 Physics, Chemistry, Biology'),
    (r'(?i)(english|writing|grammar|literature|language)', 'Academics - Language Arts', '📚 English, Writing, Literature'),
    (r'(?i)(history|social.?studies|government|economics)', 'Academics - History & Social Studies', '🏛️ History, Economics, Government'),

    # Professional Development
    (r'(?i)(interview|resume|job.?search|career|business)', 'Professional - Career Development', '💼 Interview Prep, Career'),
    (r'(?i)(leadership|management|communication|presentation|public.?speak)', 'Professional - Leadership', '🎤 Leadership, Communication'),
    (r'(?i)(programming|coding|python|javascript|web.?dev|software)', 'Professional - Programming', '💻 Programming, Coding'),
    (r'(?i)(design|ux|ui|graphic|photography)', 'Professional - Design & Creative', '🎨 Design, Photography, UX/UI'),
    (r'(?i)(marketing|sales|business|entrepreneurship|startup)', 'Professional - Business', '📊 Marketing, Sales, Entrepreneurship'),

    # Seminars & Conferences
    (r'(?i)(seminar|conference|workshop|webinar|lecture|talk|ted)', 'Learning - Seminars & Talks', '🎤 Seminars, Conferences, TED'),
    (r'(?i)(course|lesson|tutorial|class|school)', 'Learning - Courses & Lessons', '👨‍🎓 Courses, Lessons, Tutorials'),

    # Personal Development & Self-Help
    (r'(?i)(motivation|inspirational|self.?help|personal.?growth|development)', 'Self-Improvement - Personal Growth', '🌱 Personal Growth, Motivation'),
    (r'(?i)(psychology|mindset|habits|productivity|time.?manage)', 'Self-Improvement - Psychology & Habits', '🧠 Psychology, Habits, Productivity'),
    (r'(?i)(money|finance|investing|crypto|stock)', 'Self-Improvement - Finance', '💰 Finance, Investing, Money'),
    (r'(?i)(health|wellness|mental.?health|therapy|doctor)', 'Health - General Wellness', '⚕️ Health, Wellness, Mental Health'),

    # Art & Culture
    (r'(?i)(art|painting|drawing|sculpture|museum)', 'Arts & Culture - Visual Arts', '🖼️ Art, Painting, Drawing'),
    (r'(?i)(music|instrument|guitar|piano|singing)', 'Arts & Culture - Music', '🎵 Music, Instruments'),
    (r'(?i)(film|cinema|movie.?making|director|actor)', 'Arts & Culture - Film', '🎬 Film, Cinema, Acting'),
    (r'(?i)(theater|drama|play|comedy)', 'Arts & Culture - Theater', '🎭 Theater, Drama, Comedy'),

    # Hobbies & Interests
    (r'(?i)(cooking|baking|culinary)', 'Hobbies - Cooking & Baking', '👨‍🍳 Cooking, Baking'),
    (r'(?i)(travel|adventure|tourism|geography)', 'Hobbies - Travel & Adventure', '✈️ Travel, Adventure'),
    (r'(?i)(gaming|esports|video.?game)', 'Hobbies - Gaming', '🎮 Gaming, Esports'),
    (r'(?i)(crafts|diy|woodwork|home.?improvement)', 'Hobbies - DIY & Crafts', '🛠️ DIY, Crafts, Woodworking'),
    (r'(?i)(gardening|nature|outdoors)', 'Hobbies - Gardening & Nature', '🌿 Gardening, Nature'),

    # Language Learning
    (r'(?i)(language|spanish|french|german|chinese|japanese|korean)', 'Learning - Languages', '🗣️ Languages, ESL'),

    # Uncategorized
    (r'.*', 'Uncategorized - Review Needed', '❓ Needs Manual Review'),
]


def categorize_file(filename):
    """Determine category based on filename patterns."""
    for pattern, category, description in CATEGORIES:
        if re.search(pattern, filename):
            return category, description
    return 'Uncategorized - Review Needed', '❓ Needs Manual Review'


def scan_and_categorize(learning_dir):
    """Scan folder and categorize all video files."""
    learning_path = Path(learning_dir)

    if not learning_path.exists():
        print(f"❌ Error: {learning_dir} not found")
        return

    categorized = defaultdict(list)
    total_size = 0

    # Video extensions
    VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm', '.m4v'}

    print(f"\n📂 Scanning {learning_dir}...")
    print("=" * 80)

    for item in learning_path.rglob('*'):
        if item.is_file() and item.suffix.lower() in VIDEO_EXTS:
            category, description = categorize_file(item.name)
            size = item.stat().st_size / (1024**3)  # GB
            categorized[category].append((item, description, size))
            total_size += size

    # Print summary
    print(f"\n📊 Organization Summary:")
    print(f"   Total files: {sum(len(v) for v in categorized.values())}")
    print(f"   Total size: {total_size:.1f} GB")
    print(f"   Categories found: {len(categorized)}\n")

    # Show categories with file counts
    for category in sorted(categorized.keys()):
        files = categorized[category]
        size = sum(f[2] for f in files)
        desc = files[0][1]
        print(f"   {desc}")
        print(f"      → {len(files)} files, {size:.1f} GB")

    return categorized


def create_folders(learning_dir, categorized, dry_run=True):
    """Create category folders. Set dry_run=False to actually move files."""
    learning_path = Path(learning_dir)

    print(f"\n{'🔍 DRY RUN - ' if dry_run else ''}📁 Creating folder structure...")
    print("=" * 80)

    for category, files in sorted(categorized.items()):
        if category == 'Uncategorized - Review Needed':
            continue  # Skip uncategorized for now

        # Create folder name from category
        folder_name = category.split(' - ')[0]  # First part before dash
        target_dir = learning_path / folder_name

        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n📁 {folder_name}/")

        for filepath, desc, size in files:
            rel_path = filepath.relative_to(learning_path)
            action = "→ MOVE" if not dry_run else "→ WOULD MOVE"
            print(f"   {action}: {filepath.name} ({size:.2f} GB)")

            if not dry_run:
                try:
                    shutil.move(str(filepath), str(target_dir / filepath.name))
                except Exception as e:
                    print(f"      ⚠️  Error: {e}")

    print("\n✅ Folder structure created!" if not dry_run else "\n✅ Dry run complete!")


def generate_organization_guide(categorized):
    """Generate a guide for the user."""
    guide = """
╔═══════════════════════════════════════════════════════════════════════════╗
║              LEARNING & FITNESS LIBRARY ORGANIZATION GUIDE                ║
╚═══════════════════════════════════════════════════════════════════════════╝

YOUR PROPOSED FOLDER STRUCTURE:
"""

    categories = sorted(set(c.split(' - ')[0] for c in categorized.keys()
                          if c != 'Uncategorized - Review Needed'))

    for i, cat in enumerate(categories, 1):
        guide += f"\n{i}. {cat}/"
        # Add sample subcategories based on actual data
        for full_cat, files in sorted(categorized.items()):
            if full_cat.startswith(cat):
                subcats = full_cat.split(' - ')
                if len(subcats) > 1:
                    guide += f"\n   └─ {subcats[1]} ({len(files)} items)"

    guide += f"""

NEXT STEPS:
──────────
1. Review the categorization above
2. Run this script on Windows with --organize to create folders and move files
3. (Optional) Further subdivide by season/topic within each folder:
   Example: Fitness - Strength/Week 1, Fitness - Strength/Week 2, etc.

USAGE:
──────
# Dry run (see what would happen):
python organize_learning.py --scan F:\\Plex\\Learning

# Create folders and move files:
python organize_learning.py --organize F:\\Plex\\Learning

# Show this guide:
python organize_learning.py --guide
"""

    return guide


if __name__ == '__main__':
    import sys

    if '--guide' in sys.argv:
        # Would need to load existing categorized data - placeholder
        print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║              LEARNING & FITNESS LIBRARY ORGANIZATION GUIDE                ║
╚═══════════════════════════════════════════════════════════════════════════╝

PROPOSED FOLDER STRUCTURE:
──────────────────────────

📁 Learning & Fitness/
├── 📁 Fitness - Yoga & Stretching/        🧘 Yoga, Pilates, Flexibility
├── 📁 Fitness - Strength & Cardio/        💪 Gym, Weights, HIIT, Cardio
├── 📁 Fitness - Dance/                    💃 Dance, Zumba, Ballet
├── 📁 Fitness - Running/                  🏃 Running, Jogging
├── 📁 Fitness - Sports/                   ⚽ Sports, Martial Arts
├── 📁 Health - Nutrition & Cooking/       🍎 Nutrition, Diets, Cooking
├── 📁 Wellness - Meditation/              🧠 Meditation, Mindfulness
├── 📁 Academics - Standardized Tests/     📝 GRE, SAT, ACT, LSAT
├── 📁 Academics - Mathematics/            📐 Math, Calculus
├── 📁 Academics - Sciences/               🔬 Physics, Chemistry, Biology
├── 📁 Academics - Language Arts/          📚 English, Writing
├── 📁 Academics - History & Social/       🏛️ History, Economics
├── 📁 Professional - Career/              💼 Interview, Career
├── 📁 Professional - Leadership/          🎤 Leadership, Communication
├── 📁 Professional - Programming/         💻 Programming, Coding
├── 📁 Professional - Design & Creative/   🎨 Design, Photography
├── 📁 Professional - Business/            📊 Marketing, Sales
├── 📁 Learning - Seminars & Talks/        🎤 Seminars, Conferences, TED
├── 📁 Learning - Courses & Lessons/       👨‍🎓 Courses, Tutorials
├── 📁 Self-Improvement - Personal Growth/ 🌱 Motivation, Personal Growth
├── 📁 Self-Improvement - Psychology/      🧠 Psychology, Habits, Productivity
├── 📁 Self-Improvement - Finance/         💰 Finance, Investing
├── 📁 Health - General Wellness/          ⚕️ Health, Mental Health
├── 📁 Arts & Culture - Visual Arts/       🖼️ Art, Painting
├── 📁 Arts & Culture - Music/             🎵 Music, Instruments
├── 📁 Arts & Culture - Film/              🎬 Film, Cinema
├── 📁 Arts & Culture - Theater/           🎭 Theater, Drama
├── 📁 Hobbies - Cooking & Baking/         👨‍🍳 Cooking
├── 📁 Hobbies - Travel & Adventure/       ✈️ Travel
├── 📁 Hobbies - Gaming/                   🎮 Gaming
├── 📁 Hobbies - DIY & Crafts/             🛠️ DIY, Crafts
├── 📁 Hobbies - Gardening & Nature/       🌿 Gardening
├── 📁 Learning - Languages/               🗣️ Languages, ESL
└── 📁 Uncategorized - Review Needed/      ❓ Manual review

RUNNING THE SCRIPT ON WINDOWS:
──────────────────────────────

1. Open PowerShell and navigate to PlexOptimize:
   cd C:\\PlexOptimize

2. Scan your Learning folder (dry run, no changes):
   python organize_learning.py --scan F:\\Plex\\Learning

3. Review the output and categories

4. Create folders and organize (this WILL move files):
   python organize_learning.py --organize F:\\Plex\\Learning

FURTHER CUSTOMIZATION:
──────────────────────
After running, you can manually rename/subdivide folders by topic:

Example - Fitness - Strength & Cardio/:
  ├── 01 - Beginner Program
  ├── 02 - Intermediate Strength
  ├── 03 - HIIT Sessions
  └── 04 - Recovery & Stretching

Example - Academics - Mathematics/:
  ├── Arithmetic
  ├── Algebra
  ├── Geometry
  ├── Calculus
  └── Statistics

Example - Learning - Seminars & Talks/:
  ├── TED Talks
  ├── Conferences 2024
  ├── Webinars
  └── Expert Lectures
""")
    elif '--scan' in sys.argv:
        learning_dir = sys.argv[sys.argv.index('--scan') + 1]
        categorized = scan_and_categorize(learning_dir)
        create_folders(learning_dir, categorized, dry_run=True)
    elif '--organize' in sys.argv:
        learning_dir = sys.argv[sys.argv.index('--organize') + 1]
        categorized = scan_and_categorize(learning_dir)
        response = input("\n⚠️  This will MOVE files. Continue? (yes/no): ")
        if response.lower() == 'yes':
            create_folders(learning_dir, categorized, dry_run=False)
        else:
            print("Cancelled.")
    else:
        print("PlexOptimize Learning & Fitness Organizer")
        print("Usage:")
        print("  python organize_learning.py --guide              (show this guide)")
        print("  python organize_learning.py --scan <path>       (dry run)")
        print("  python organize_learning.py --organize <path>   (actually move files)")
        print("\nExample:")
        print("  python organize_learning.py --scan F:\\Plex\\Learning")
