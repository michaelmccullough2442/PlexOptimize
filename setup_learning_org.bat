@echo off
REM PlexOptimize Learning & Fitness Organization Setup
REM Run this from C:\PlexOptimize

cls
echo.
echo =====================================================================
echo   PlexOptimize Learning and Fitness Library Organizer
echo =====================================================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Please install Python from: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [OK] Python is installed
echo.

REM Check if organize_learning.py exists
if not exist organize_learning.py (
    echo ERROR: organize_learning.py not found!
    echo Make sure you are in C:\PlexOptimize
    pause
    exit /b 1
)

echo [OK] organize_learning.py found
echo.

echo =====================================================================
echo Step 1: Preview (Dry Run - No changes will be made)
echo =====================================================================
echo.
set /p proceed="Ready to scan your Learning folder? (yes/no): "

if /i "%proceed%"=="yes" (
    echo.
    echo Scanning F:\Plex\Learning...
    python organize_learning.py --scan F:\Plex\Learning
) else (
    echo Skipping scan.
)

echo.
echo =====================================================================
echo Step 2: View Categorization Guide
echo =====================================================================
echo.
set /p viewguide="View the categorization guide? (yes/no): "

if /i "%viewguide%"=="yes" (
    python organize_learning.py --guide
)

echo.
echo =====================================================================
echo Step 3: Ready to Organize?
echo =====================================================================
echo.
echo This will CREATE new folders and MOVE files into:
echo   - Fitness - Strength and Cardio
echo   - Academics - Mathematics
echo   - Professional - Career
echo   - And many more categories
echo.
set /p organize="Proceed with automatic organization? (yes/no): "

if /i "%organize%"=="yes" (
    echo.
    echo WARNING: Files will be MOVED. Type YES to confirm.
    set /p confirm="Confirm (YES/no): "

    if /i "%confirm%"=="YES" (
        echo.
        echo Starting organization...
        python organize_learning.py --organize F:\Plex\Learning
        echo.
        echo =====================================================================
        echo SUCCESS! Your Learning folder is now organized.
        echo =====================================================================
        echo.
        echo Next steps:
        echo   1. Open F:\Plex\Learning in File Explorer
        echo   2. Review the new folder structure
        echo   3. Optional: Create subfolders within categories (Week 1, Week 2, etc)
        echo   4. Plex will automatically detect the new organization
        echo.
    ) else (
        echo Cancelled - no files were moved.
    )
) else (
    echo Skipping automatic organization.
    echo You can run it later with:
    echo   python organize_learning.py --organize F:\Plex\Learning
)

echo.
pause
