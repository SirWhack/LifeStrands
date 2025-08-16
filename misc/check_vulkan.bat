@echo off
echo Checking Vulkan SDK installation...
echo.

echo Testing vulkaninfo command:
vulkaninfo --version
if %errorlevel% equ 0 (
    echo [OK] vulkaninfo found
) else (
    echo [ERROR] vulkaninfo not found
)

echo.
echo Checking environment variables:
echo VULKAN_SDK: %VULKAN_SDK%

echo.
echo Checking PATH for Vulkan:
where vulkaninfo

echo.
echo Testing Vulkan device enumeration:
vulkaninfo --summary 2>nul
if %errorlevel% equ 0 (
    echo [OK] Vulkan devices detected
) else (
    echo [WARN] No Vulkan devices or driver issues
)

pause