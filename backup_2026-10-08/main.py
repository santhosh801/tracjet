import customtkinter as ctk
from ui import AppUI

if __name__ == "__main__":
    ctk.set_appearance_mode("Light")
    ctk.set_default_color_theme("blue")
    app = AppUI()
    app.mainloop()
