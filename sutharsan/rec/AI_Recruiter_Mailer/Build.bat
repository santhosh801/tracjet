@echo off
echo Building Tracjet...
pip install -r requirements.txt
python -m unittest discover -s tests
pyinstaller --noconfirm --onedir --windowed --name "Tracjet" "main.py"
echo Build Complete! Check the 'dist\Tracjet' folder.
pause
