@echo off
REM Start the Galatea WebSocket server and print Godot launch instructions.
cd /d "%~dp0"

echo Starting Galatea WebSocket server...
start /b uv run python -m server --stub

timeout /t 2 /nobreak > nul

echo.
echo ==========================================================
echo   Server running on ws://localhost:8765  (StubRunner mode)
echo.
echo   Open the Godot 4 editor and load:  client\
echo   Then press F5 (Play) to launch the game.
echo.
echo   To use a real LLM: run_server.bat --no-stub
echo ==========================================================
echo.
echo Press Ctrl+C to stop the server.
pause
