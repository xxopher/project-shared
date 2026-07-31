@echo off
title Cleaning Up Property Report Folder & Syncing GitHub
color 0B
echo ===================================================================
echo   SINGAPORE PROPERTY MARKET 2026: CLEANUP & GITHUB SYNC UTILITY
echo ===================================================================
echo.
echo [1/3] Removing intermediate development assets locally...
echo - test_api.js, test_offset.js, test_sql.js
echo - find_start.js, analyze_hdb.js
echo - styles.css, app.js
echo - gemini-report.html
echo - deploy.bat
echo.

del /f /q test_api.js test_offset.js test_sql.js find_start.js analyze_hdb.js styles.css app.js gemini-report.html deploy.bat >nul 2>&1
echo Done local cleanup.
echo.

echo [2/3] Committing deletions in Git...
git add -A
git commit -m "build: clean up intermediate development files and keep only essential deliverables"
echo.

echo [3/3] Syncing deletions with GitHub (main branch)...
git push origin main
echo.

if %errorlevel% equ 0 (
    color 0A
    echo ===================================================================
    echo   SUCCESS! Your GitHub repository is now completely cleaned up!
    echo ===================================================================
    echo.
) else (
    color 0E
    echo ===================================================================
    echo   SYNC ENCOUNTERED ISSUES
    echo ===================================================================
    echo.
    echo Git could not push the cleanup commit. Please ensure your local repo
    echo is fully authorized and push again manually.
    echo.
)

echo This script will now self-delete to leave your local folder spotless.
pause

:: Elegant self-deletion trick
(goto) 2>nul & del "%~f0"
