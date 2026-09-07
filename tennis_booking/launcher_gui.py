# 바탕화면 아이콘으로 띄우는 간단한 실행/종료 UI.
# remote_launcher.py를 자식 프로세스로 실행/종료만 담당하고, 출력(모바일 링크 등)은 창 안에 그대로 보여준다.

import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
# pythonw.exe(콘솔 없음)로 이 GUI를 띄워도 자식 프로세스는 출력을 파이프로 받을 거라
# python.exe든 pythonw.exe든 상관없지만, 있으면 python.exe를 우선 사용한다.
PYTHON_EXE = shutil.which("python") or sys.executable


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("테니스 예약 서버")
        root.geometry("560x380")

        self.proc: subprocess.Popen | None = None

        self.status_var = tk.StringVar(value="꺼짐")
        tk.Label(root, textvariable=self.status_var, font=("맑은 고딕", 14, "bold")).pack(pady=8)

        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=4)
        self.start_btn = tk.Button(btn_frame, text="실행", width=14, height=2, command=self.start)
        self.start_btn.grid(row=0, column=0, padx=8)
        self.stop_btn = tk.Button(btn_frame, text="종료", width=14, height=2, command=self.stop, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=1, padx=8)

        self.log = tk.Text(root, height=16, width=68, state=tk.DISABLED)
        self.log.pack(padx=10, pady=10, fill="both", expand=True)

        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def append_log(self, text: str) -> None:
        self.log.config(state=tk.NORMAL)
        self.log.insert("end", text)
        self.log.see("end")
        self.log.config(state=tk.DISABLED)

    def start(self) -> None:
        if self.proc is not None:
            return
        self.append_log("서버 시작 중...\n")
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        self.proc = subprocess.Popen(
            [PYTHON_EXE, "-u", "remote_launcher.py"],
            cwd=str(SCRIPT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.status_var.set("실행 중")
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(target=self._read_output, args=(self.proc,), daemon=True).start()

    def _read_output(self, proc: subprocess.Popen) -> None:
        if proc.stdout is not None:
            for line in proc.stdout:
                self.root.after(0, self.append_log, line)
        self.root.after(0, self._on_process_exit, proc)

    def _on_process_exit(self, proc: subprocess.Popen) -> None:
        if self.proc is not proc:
            return  # 이미 stop()으로 정리된 뒤 들어온 늦은 콜백
        self.status_var.set("꺼짐")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.proc = None

    def stop(self) -> None:
        if self.proc is None:
            return
        self.append_log("\n서버 종료 중...\n")
        proc, self.proc = self.proc, None
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        # remote_launcher.py가 띄운 ngrok 터널(별도 프로세스)은 python을 죽여도 안 따라 죽으므로 함께 정리한다.
        subprocess.run(["taskkill", "/IM", "ngrok.exe", "/F"], capture_output=True)
        self.status_var.set("꺼짐")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.append_log("서버 종료 완료.\n")

    def on_close(self) -> None:
        if self.proc is not None:
            self.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
