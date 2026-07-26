import tkinter as tk
from tkinter import messagebox, simpledialog


class BookInfoDialog(simpledialog.Dialog):
    def __init__(self, parent, title, initialvalue):
        self.initialvalue = initialvalue
        self.result_title = None
        self.result_direction = None
        self.result_expected_pages = None
        super().__init__(parent, title)

    def body(self, master):
        tk.Label(master, text="タイトル:").grid(
            row=0, column=0, sticky="w", padx=5, pady=5
        )
        self.e_title = tk.Entry(master, width=50)
        self.e_title.insert(0, self.initialvalue)
        self.e_title.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(master, text="ページめくり:").grid(
            row=1, column=0, sticky="w", padx=5, pady=5
        )

        self.var_direction = tk.StringVar(value="left")
        frame_dir = tk.Frame(master)
        frame_dir.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        tk.Radiobutton(
            frame_dir,
            text="左キー (縦書き/右開き)",
            variable=self.var_direction,
            value="left",
        ).pack(side="left", padx=5)
        tk.Radiobutton(
            frame_dir,
            text="右キー (横書き/左開き)",
            variable=self.var_direction,
            value="right",
        ).pack(side="left", padx=5)

        tk.Label(master, text="撮影画面数（任意・通常は空欄）:").grid(
            row=2, column=0, sticky="w", padx=5, pady=5
        )
        self.e_expected_pages = tk.Entry(master, width=12)
        self.e_expected_pages.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        return self.e_title

    def validate(self):
        raw_value = self.e_expected_pages.get().strip()
        if raw_value and (not raw_value.isdecimal() or int(raw_value) <= 0):
            messagebox.showwarning(
                "入力エラー",
                "撮影画面数には1以上の整数を入力するか、空欄にしてください。",
                parent=self,
            )
            return False
        return True

    def apply(self):
        self.result_title = self.e_title.get()
        self.result_direction = self.var_direction.get()
        raw_value = self.e_expected_pages.get().strip()
        self.result_expected_pages = int(raw_value) if raw_value else None
