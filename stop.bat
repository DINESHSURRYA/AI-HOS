@echo off
title AI-HOS Stopper
echo Stopping all AI-HOS service windows...
taskkill /FI "WINDOWTITLE eq AI-HOS Clinical Doc AI*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq AI-HOS Prior Auth Engine*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq AI-HOS Dashboard*" /T /F >nul 2>&1
echo Done! All AI-HOS services have been stopped.
