@echo off
echo Building AI Recruiter Mailer...
pip install -r requirements.txt
pyinstaller --noconfirm --onedir --windowed --name "AI_Recruiter_Mailer" "main.py"
echo Build Complete! Check the 'dist' folder.
pause
