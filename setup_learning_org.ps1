# PlexOptimize Learning & Fitness Organization Setup
# Run on Windows PowerShell in C:\PlexOptimize

Write-Host "╔═══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   PlexOptimize Learning & Fitness Library Organizer          ║" -ForegroundColor Cyan
Write-Host "║   Setup Script                                              ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Check if we're in the right directory
if (-not (Test-Path "organize_learning.py")) {
    Write-Host "❌ Error: organize_learning.py not found!" -ForegroundColor Red
    Write-Host "   Make sure you're in C:\PlexOptimize" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Found organize_learning.py" -ForegroundColor Green
Write-Host ""

# Check Python
Write-Host "🔍 Checking Python installation..." -ForegroundColor Cyan
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found! Install from:" -ForegroundColor Red
    Write-Host "   https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "STEP 1: Preview Organization (Dry Run)" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "This will scan your Learning folder and show you:"
Write-Host "  • How many videos in each category"
Write-Host "  • Proposed folder structure"
Write-Host "  • Size of each category"
Write-Host "  • NO FILES WILL BE MOVED" -ForegroundColor Green
Write-Host ""

$readyForScan = Read-Host "Ready to scan? (yes/no)"
if ($readyForScan -eq "yes") {
    Write-Host ""
    Write-Host "🔄 Scanning F:\Plex\Learning..." -ForegroundColor Cyan
    python organize_learning.py --scan F:\Plex\Learning

    Write-Host ""
    Write-Host "✅ Scan complete!" -ForegroundColor Green
} else {
    Write-Host "⏭️  Skipping scan..." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "STEP 2: View Categorization Guide" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

$viewGuide = Read-Host "View categorization guide? (yes/no)"
if ($viewGuide -eq "yes") {
    python organize_learning.py --guide
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "STEP 3: Review and Decide" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "📋 You now have two options:"
Write-Host ""
Write-Host "  Option A: Manual Review"
Write-Host "    • Review files in F:\Plex\Learning"
Write-Host "    • Manually rename/organize as needed"
Write-Host "    • Custom organization based on your preferences"
Write-Host ""
Write-Host "  Option B: Automatic Organization"
Write-Host "    • Let the script organize by category"
Write-Host "    • Creates folders and moves files automatically"
Write-Host "    • ⚠️  Files WILL be moved (this is permanent)"
Write-Host ""

$proceed = Read-Host "Proceed with automatic organization? (yes/no)"

if ($proceed -eq "yes") {
    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "STEP 4: Execute Organization" -ForegroundColor Yellow
    Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "⚠️  WARNING: This will MOVE files into new folder structure!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Once started, the operation cannot be easily undone."
    Write-Host "Files will be organized into folders like:"
    Write-Host "  • Fitness - Strength & Cardio\"
    Write-Host "  • Academics - Mathematics\"
    Write-Host "  • Professional - Career\"
    Write-Host "  • Learning - Seminars & Talks\"
    Write-Host "  ...and more"
    Write-Host ""

    $finalConfirm = Read-Host "Type 'YES' to proceed (all caps)"

    if ($finalConfirm -eq "YES") {
        Write-Host ""
        Write-Host "🚀 Starting organization..." -ForegroundColor Green
        python organize_learning.py --organize F:\Plex\Learning

        Write-Host ""
        Write-Host "╔═══════════════════════════════════════════════════════════════╗" -ForegroundColor Green
        Write-Host "║                    ✅ ORGANIZATION COMPLETE!                  ║" -ForegroundColor Green
        Write-Host "╚═══════════════════════════════════════════════════════════════╝" -ForegroundColor Green
        Write-Host ""
        Write-Host "Your Learning folder is now organized into categories."
        Write-Host ""
        Write-Host "📁 Next steps:" -ForegroundColor Yellow
        Write-Host "  1. Open F:\Plex\Learning in File Explorer"
        Write-Host "  2. Review the folder structure"
        Write-Host "  3. (Optional) Rename folders to your preference"
        Write-Host "  4. (Optional) Create subfolders by season/topic within categories"
        Write-Host "  5. Plex will automatically refresh and show new folders"
        Write-Host ""
        Write-Host "💡 Tips for further organization:" -ForegroundColor Cyan
        Write-Host "  • In Fitness folders: create Week 1, Week 2, etc."
        Write-Host "  • In Academics: create subfolders for each subject"
        Write-Host "  • In Seminars: organize by year or topic"
        Write-Host ""
    } else {
        Write-Host "❌ Cancelled. No files were moved." -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "⏭️  Skipping automatic organization." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "You can run the organization anytime with:"
    Write-Host "  python organize_learning.py --organize F:\Plex\Learning"
    Write-Host ""
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
