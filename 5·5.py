import sys
import time
import tkinter as tk
from tkinter import messagebox, ttk, simpledialog
import threading
import random
import re
import os
import pickle
from collections import deque
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

# ================== 正确的模式数据库 ==================
class PatternDatabase:
    def __init__(self, numbers, size=5, db_dir="pdb_cache", load_if_exists=True):
        self.size = size
        self.n = size * size
        self.numbers = sorted(numbers)
        self.num_set = set(self.numbers)
        
        os.makedirs(db_dir, exist_ok=True)
        self.db_file = os.path.join(db_dir, f"pdb_{'_'.join(map(str,self.numbers))}.bin")
        
        self.db = {}
        
        if load_if_exists and os.path.exists(self.db_file):
            # 检查文件大小是否合理（每个状态约72字节，70万状态约50MB）
            if os.path.getsize(self.db_file) > 10 * 1024 * 1024:  # 大于10MB
                with open(self.db_file, 'rb') as f:
                    self.db = pickle.load(f)
                print(f"加载数据库 {self.numbers}，共 {len(self.db)} 个状态")
                return
        
        self._build()
        with open(self.db_file, 'wb') as f:
            pickle.dump(self.db, f)
    
    def _encode(self, positions):
        """将位置列表编码为整数（每个位置5bit）"""
        state = 0
        for i, pos in enumerate(positions):
            state |= (pos << (i * 5))
        return state
    
    def _decode(self, pattern, num_numbers):
        """解码为位置列表"""
        positions = []
        temp = pattern
        for i in range(num_numbers):
            positions.append(temp & 0x1F)
            temp >>= 5
        return positions
    
    def _get_goal_positions(self):
        """目标状态下，pattern中数字的位置"""
        goal_board = list(range(1, self.n)) + [0]
        positions = []
        for num in self.numbers:
            positions.append(goal_board.index(num))
        return positions
    
    def _get_memory_usage(self):
        try:
            import psutil
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except:
            return 0
    
    def _build(self):
        """正确的BFS：状态为 (pattern编码, 空格位置)"""
        start_positions = self._get_goal_positions()
        start_pattern = self._encode(start_positions)
        
        self.db = {start_pattern: 0}
        # visited 存储 (pattern, blank)
        visited = set()
        visited.add((start_pattern, self.n - 1))
        # 队列存储 (positions列表, blank, steps)
        queue = deque([(start_positions, self.n - 1, 0)])
        
        dirs = [(-1,0), (1,0), (0,-1), (0,1)]
        batch_count = 0
        
        # 理论最大状态数：C(25,6) * 19 ≈ 3.36M
        max_states = 177100 * 19
        
        while queue:
            positions, blank, steps = queue.popleft()
            
            r, c = divmod(blank, self.size)
            
            for dr, dc in dirs:
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.size and 0 <= nc < self.size:
                    new_blank = nr * self.size + nc
                    new_positions = positions[:]  # 复制
                    
                    # 如果移动的数字在pattern中，更新位置
                    if new_blank in new_positions:
                        idx = new_positions.index(new_blank)
                        new_positions[idx] = blank
                    
                    new_pattern = self._encode(new_positions)
                    state_key = (new_pattern, new_blank)
                    
                    if state_key not in visited:
                        visited.add(state_key)
                        new_steps = steps + 1
                        # 更新pattern的最小步数
                        if new_pattern not in self.db or self.db[new_pattern] > new_steps:
                            self.db[new_pattern] = new_steps
                        queue.append((new_positions, new_blank, new_steps))
            
            batch_count += 1
            if batch_count % 50000 == 0:
                mem = self._get_memory_usage()
                progress = len(visited) / max_states * 100
                print(f"[进程 {os.getpid()}] {self.numbers} 进度: {progress:.1f}% "
                      f"({len(visited)}/{max_states}), pattern数: {len(self.db)}, 内存: {mem:.1f}MB")
        
        print(f"[进程 {os.getpid()}] {self.numbers} 构建完成，共 {len(self.db)} 个pattern状态")
    
    def heuristic(self, board):
        """计算当前棋盘关于该模式数据库的启发值"""
        positions = []
        for num in self.numbers:
            pos = board.index(num)
            positions.append(pos)
        pattern = self._encode(positions)
        return self.db.get(pattern, 0)


def build_database_worker(pattern, size, db_dir):
    """工作进程：构建单个数据库（若已存在则直接加载）"""
    db = PatternDatabase(pattern, size, db_dir, load_if_exists=True)
    return pattern, len(db.db)


# ================== 固定4个数据库的管理器 ==================
class PatternDatabaseManager:
    FIXED_PATTERNS = [
        [1, 2, 3, 4, 5, 6],
        [7, 8, 9, 10, 11, 12],
        [13, 14, 15, 16, 17, 18],
        [19, 20, 21, 22, 23, 24]
    ]
    
    def __init__(self, size=5):
        self.size = size
        self.patterns = self.FIXED_PATTERNS
        self.databases = []
        self.ready = False
    
    def build_all_async(self, progress_callback=None, max_workers=2):
        """并发构建数据库（每个数据库独立进程）"""
        cpu_count = min(os.cpu_count(), max_workers)
        with ProcessPoolExecutor(max_workers=cpu_count) as executor:
            futures = {
                executor.submit(build_database_worker, pattern, self.size, "pdb_cache"): pattern 
                for pattern in self.patterns
            }
            for future in as_completed(futures):
                pattern = futures[future]
                try:
                    pattern, state_count = future.result()
                    db = PatternDatabase(pattern, self.size, load_if_exists=True)
                    self.databases.append(db)
                    if progress_callback:
                        progress_callback(len(self.databases), len(self.patterns), pattern)
                except Exception as e:
                    print(f"构建数据库 {pattern} 失败: {e}")
        self.ready = True
    
    def heuristic(self, board):
        """累加所有数据库的启发值"""
        if not self.ready:
            return 0
        total = 0
        for db in self.databases:
            total += db.heuristic(board)
        return total


# ================== 求解器 ==================
class FastPuzzleSolver:
    def __init__(self, start_board, size=5, db_manager=None):
        self.size = size
        self.n = size * size
        self.start = start_board[:]
        self.goal = list(range(1, self.n)) + [0]
        self.goal_pos = {val: (idx // size, idx % size) for idx, val in enumerate(self.goal) if val != 0}
        self.rev_move = {'U':'D','D':'U','L':'R','R':'L'}
        self.db_manager = db_manager
        self.h_cache = {}
    
    def manhattan(self, board):
        dist = 0
        for i, val in enumerate(board):
            if val != 0:
                r, c = divmod(i, self.size)
                tr, tc = self.goal_pos[val]
                dist += abs(r - tr) + abs(c - tc)
        return dist
    
    def heuristic(self, board):
        key = tuple(board)
        if key in self.h_cache:
            return self.h_cache[key]
        h = self.manhattan(board)
        if self.db_manager and self.db_manager.ready:
            h = max(h, self.db_manager.heuristic(board))
        if len(self.h_cache) > 100000:
            self.h_cache.clear()
        self.h_cache[key] = h
        return h
    
    def get_neighbors(self, board, last_move):
        zero = board.index(0)
        r, c = divmod(zero, self.size)
        neighbors = []
        for dr, dc, move in [(-1,0,'U'), (1,0,'D'), (0,-1,'L'), (0,1,'R')]:
            nr, nc = r+dr, c+dc
            if 0 <= nr < self.size and 0 <= nc < self.size:
                if last_move and move == self.rev_move[last_move]:
                    continue
                new_board = board[:]
                target = nr * self.size + nc
                new_board[zero], new_board[target] = new_board[target], new_board[zero]
                neighbors.append((new_board, move))
        # 按启发值排序，优先探索更有希望的节点
        neighbors.sort(key=lambda x: self.heuristic(x[0]))
        return neighbors
    
    def ida_star(self, progress_callback=None):
        threshold = self.heuristic(self.start)
        self.nodes_expanded = 0
        self.path = []
        while True:
            self.next_threshold = float('inf')
            found = self._search(self.start, 0, threshold, None)
            if found:
                return self.path, self.nodes_expanded
            if self.next_threshold == float('inf'):
                return None, self.nodes_expanded
            threshold = self.next_threshold
            if progress_callback:
                progress_callback(self.nodes_expanded, threshold, 0)
    
    def _search(self, board, g, threshold, last_move):
        f = g + self.heuristic(board)
        if f > threshold:
            if f < self.next_threshold:
                self.next_threshold = f
            return False
        if board == self.goal:
            return True
        for new_board, move in self.get_neighbors(board, last_move):
            self.nodes_expanded += 1
            self.path.append(move)
            if self._search(new_board, g+1, threshold, move):
                return True
            self.path.pop()
        return False
    
    def solve(self, progress_callback=None):
        return self.ida_star(progress_callback)


# ================== GUI 界面 ==================
class SimplePuzzleGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("数字华容道 - 5x5 正确模式数据库版")
        self.root.geometry("1200x850")
        self.board = list(range(1, 25)) + [0]
        self.solution_moves = []
        self.detailed_moves = []
        self.current_step = 0
        self.auto_playing = False
        self.solving = False
        self.steps_count = 0
        self.db_manager = None
        self.db_building = False
        self.colors = {
            'bg': '#2C3E50', 'button_bg': '#34495E', 'button_fg': '#ECF0F1',
            'empty_bg': '#95A5A6', 'button_active_bg': '#5D6D7E',
            'solve_btn': '#27AE60', 'reset_btn': '#E74C3C',
            'step_btn': '#3498DB', 'input_btn': '#9B59B6'
        }
        self.setup_ui()
        self.add_info("欢迎使用5x5数字华容道求解器（正确模式数据库版）")
        self.add_info("使用4个互斥数据库，每组6个数字")
        self.add_info("内存优化：每个数据库约600-800MB，顺序构建")
        self.start_db_building()
    
    def setup_ui(self):
        self.root.configure(bg=self.colors['bg'])
        main_frame = tk.Frame(self.root, bg=self.colors['bg'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        left_frame = tk.Frame(main_frame, bg=self.colors['bg'])
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        title_label = tk.Label(left_frame, text="数字华容道求解器 (5x5)\n正确模式数据库版",
                               font=("微软雅黑", 16, "bold"), fg="#ECF0F1", bg=self.colors['bg'])
        title_label.pack(pady=10)
        self.game_frame = tk.Frame(left_frame, bg=self.colors['bg'])
        self.game_frame.pack(pady=20)
        self.buttons = [[None for _ in range(5)] for _ in range(5)]
        for i in range(5):
            for j in range(5):
                self.create_button(i, j)
        info_frame = tk.Frame(left_frame, bg=self.colors['bg'])
        info_frame.pack(pady=10)
        self.steps_label = tk.Label(info_frame, text="步数: 0", font=("微软雅黑", 12), fg="#ECF0F1", bg=self.colors['bg'])
        self.steps_label.pack(side=tk.LEFT, padx=20)
        self.status_label = tk.Label(info_frame, text="状态: 启动中...", font=("微软雅黑", 12), fg="#F39C12", bg=self.colors['bg'])
        self.status_label.pack(side=tk.LEFT, padx=20)
        control_frame = tk.Frame(left_frame, bg=self.colors['bg'])
        control_frame.pack(pady=20)
        btn_frame1 = tk.Frame(control_frame, bg=self.colors['bg'])
        btn_frame1.pack(pady=5)
        self.input_btn = tk.Button(btn_frame1, text="📝 输入棋盘", command=self.input_board,
                                   font=("微软雅黑",10,"bold"), bg=self.colors['input_btn'], fg="white", padx=12, pady=6, cursor="hand2")
        self.input_btn.pack(side=tk.LEFT, padx=5)
        self.solve_btn = tk.Button(btn_frame1, text="🔍 自动求解", command=self.solve_puzzle,
                                   font=("微软雅黑",10,"bold"), bg=self.colors['solve_btn'], fg="white", padx=12, pady=6, cursor="hand2")
        self.solve_btn.pack(side=tk.LEFT, padx=5)
        self.reset_btn = tk.Button(btn_frame1, text="🔄 重置", command=self.reset_puzzle,
                                   font=("微软雅黑",10,"bold"), bg=self.colors['reset_btn'], fg="white", padx=12, pady=6, cursor="hand2")
        self.reset_btn.pack(side=tk.LEFT, padx=5)
        self.shuffle_btn = tk.Button(btn_frame1, text="🎲 随机打乱", command=self.shuffle_puzzle,
                                     font=("微软雅黑",10,"bold"), bg=self.colors['step_btn'], fg="white", padx=12, pady=6, cursor="hand2")
        self.shuffle_btn.pack(side=tk.LEFT, padx=5)
        btn_frame2 = tk.Frame(control_frame, bg=self.colors['bg'])
        btn_frame2.pack(pady=5)
        self.prev_btn = tk.Button(btn_frame2, text="◀ 上一步", command=self.prev_step,
                                  font=("微软雅黑",10), bg=self.colors['step_btn'], fg="white", padx=12, pady=6, cursor="hand2", state=tk.DISABLED)
        self.prev_btn.pack(side=tk.LEFT, padx=5)
        self.next_btn = tk.Button(btn_frame2, text="下一步 ▶", command=self.next_step,
                                  font=("微软雅黑",10), bg=self.colors['step_btn'], fg="white", padx=12, pady=6, cursor="hand2", state=tk.DISABLED)
        self.next_btn.pack(side=tk.LEFT, padx=5)
        self.auto_btn = tk.Button(btn_frame2, text="▶ 自动播放", command=self.auto_play,
                                  font=("微软雅黑",10), bg=self.colors['step_btn'], fg="white", padx=12, pady=6, cursor="hand2", state=tk.DISABLED)
        self.auto_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = tk.Button(btn_frame2, text="⏹ 停止", command=self.stop_auto_play,
                                  font=("微软雅黑",10), bg="#E67E22", fg="white", padx=12, pady=6, cursor="hand2", state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        self.progress = ttk.Progressbar(left_frame, length=400, mode='determinate')
        self.progress.pack(pady=10)
        right_frame = tk.Frame(main_frame, bg=self.colors['bg'], width=450)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10,0))
        right_frame.pack_propagate(False)
        steps_title = tk.Label(right_frame, text="📋 求解步骤", font=("微软雅黑",14,"bold"), fg="#ECF0F1", bg=self.colors['bg'])
        steps_title.pack(pady=10)
        self.steps_info_label = tk.Label(right_frame, text="共 0 步", font=("微软雅黑",10), fg="#3498DB", bg=self.colors['bg'])
        self.steps_info_label.pack()
        steps_list_frame = tk.Frame(right_frame, bg=self.colors['bg'])
        steps_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        scrollbar = tk.Scrollbar(steps_list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.steps_listbox = tk.Listbox(steps_list_frame, font=("Consolas",11), bg="#34495E", fg="#ECF0F1",
                                        selectmode=tk.SINGLE, yscrollcommand=scrollbar.set, height=12)
        self.steps_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.steps_listbox.yview)
        self.steps_listbox.bind('<ButtonRelease-1>', self.on_step_selected)
        preview_frame = tk.Frame(right_frame, bg=self.colors['bg'], relief=tk.GROOVE, bd=2)
        preview_frame.pack(fill=tk.BOTH, pady=10, padx=5)
        preview_title = tk.Label(preview_frame, text="棋盘状态预览", font=("微软雅黑",10,"bold"), fg="#ECF0F1", bg=self.colors['bg'])
        preview_title.pack(pady=5)
        self.preview_text = tk.Text(preview_frame, height=10, width=35, font=("Courier New",11),
                                    bg="#1E2A38", fg="#ECF0F1", wrap=tk.NONE, state=tk.DISABLED)
        self.preview_text.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)
        info_text_frame = tk.Frame(left_frame, bg=self.colors['bg'])
        info_text_frame.pack(pady=10, fill=tk.X)
        tk.Label(info_text_frame, text="运行日志:", font=("微软雅黑",10,"bold"), fg="#ECF0F1", bg=self.colors['bg']).pack(anchor=tk.W)
        self.info_text = tk.Text(info_text_frame, height=5, width=60, font=("微软雅黑",9), wrap=tk.WORD)
        self.info_text.pack(fill=tk.X, pady=5)
    
    def add_info(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.info_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.info_text.see(tk.END)
        self.root.update_idletasks()
    
    def create_button(self, i, j):
        value = self.board[i*5 + j]
        text = str(value) if value != 0 else ""
        btn = tk.Button(self.game_frame, text=text, width=4, height=2, font=("Arial",16,"bold"),
                        command=lambda i=i, j=j: self.move_tile(i,j))
        if value == 0:
            btn.configure(bg=self.colors['empty_bg'], state=tk.DISABLED)
        else:
            btn.configure(bg=self.colors['button_bg'], fg=self.colors['button_fg'],
                         activebackground=self.colors['button_active_bg'])
        btn.grid(row=i, column=j, padx=2, pady=2)
        self.buttons[i][j] = btn
    
    def update_board(self):
        for i in range(5):
            for j in range(5):
                value = self.board[i*5 + j]
                text = str(value) if value != 0 else ""
                btn = self.buttons[i][j]
                btn.configure(text=text)
                if value == 0:
                    btn.configure(bg=self.colors['empty_bg'], state=tk.DISABLED)
                else:
                    btn.configure(bg=self.colors['button_bg'], fg=self.colors['button_fg'], state=tk.NORMAL)
        self.steps_label.configure(text=f"步数: {self.steps_count}")
        if self.board == list(range(1,25)) + [0]:
            messagebox.showinfo("恭喜！", "你赢了！🎉")
            self.status_label.configure(text="状态: 胜利!", fg="#2ECC71")
            self.add_info("🎉 恭喜！成功完成拼图！")
            if self.auto_playing:
                self.stop_auto_play()
    
    def format_board_text(self, board):
        lines = []
        for i in range(5):
            row = []
            for j in range(5):
                val = board[i*5 + j]
                row.append(f"{val:2d}" if val != 0 else " X")
            lines.append(" ".join(row))
        return "\n".join(lines)
    
    def update_preview(self, board):
        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete(1.0, tk.END)
        self.preview_text.insert(tk.END, self.format_board_text(board))
        self.preview_text.config(state=tk.DISABLED)
    
    def generate_detailed_moves(self, initial_board, moves):
        detailed = []
        board = initial_board[:]
        for move in moves:
            zero = board.index(0)
            zi, zj = zero//5, zero%5
            if move == 'U': target = (zi-1)*5+zj
            elif move == 'D': target = (zi+1)*5+zj
            elif move == 'L': target = zi*5+(zj-1)
            else: target = zi*5+(zj+1)
            moved = board[target]
            detailed.append((move, moved))
            board[zero], board[target] = board[target], board[zero]
        return detailed
    
    def display_solution_steps(self):
        self.steps_listbox.delete(0, tk.END)
        if not self.detailed_moves:
            self.steps_info_label.configure(text="共 0 步")
            return
        self.steps_info_label.configure(text=f"共 {len(self.detailed_moves)} 步")
        for i, (move, num) in enumerate(self.detailed_moves, 1):
            self.steps_listbox.insert(tk.END, f"步骤 {i:3d}: 移动 {move}（移动数字 {num}）")
        if self.current_step > 0:
            self.steps_listbox.selection_clear(0, tk.END)
            self.steps_listbox.selection_set(self.current_step-1)
            self.steps_listbox.see(self.current_step-1)
    
    def on_step_selected(self, event):
        if not self.detailed_moves:
            return
        sel = self.steps_listbox.curselection()
        if sel:
            target = sel[0] + 1
            if target != self.current_step:
                self.jump_to_step(target)
    
    def jump_to_step(self, target_step):
        if target_step < 0 or target_step > len(self.detailed_moves):
            return
        original = self.get_initial_board()
        self.board = original[:]
        self.steps_count = 0
        for i in range(target_step):
            self.execute_move(self.solution_moves[i], update=False)
        self.current_step = target_step
        self.update_board()
        self.progress['value'] = self.current_step
        self.update_preview(self.board)
        self.steps_listbox.selection_clear(0, tk.END)
        if target_step > 0:
            self.steps_listbox.selection_set(target_step-1)
            self.steps_listbox.see(target_step-1)
        self.status_label.configure(text=f"状态: 第{target_step}步", fg="#F39C12")
    
    def input_board(self):
        if self.solving or self.auto_playing:
            messagebox.showwarning("提示", "请等待当前操作完成")
            return
        input_text = simpledialog.askstring("输入棋盘", "请输入25个数字（空格分隔）\n空白块用0或X表示\n\n示例：1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 0", parent=self.root)
        if not input_text:
            return
        try:
            input_text = re.sub(r'[,\n\r]+', ' ', input_text)
            parts = input_text.split()
            if len(parts) != 25:
                messagebox.showerror("错误", f"需要25个数字，但收到了{len(parts)}个！")
                return
            board = []
            for p in parts:
                pu = p.upper()
                if pu == 'X' or pu == '' or p == '0':
                    board.append(0)
                else:
                    val = int(p)
                    if val < 1 or val > 24:
                        raise ValueError
                    board.append(val)
            if sorted(board) != list(range(25)):
                messagebox.showerror("错误", "数字必须包含0-24各一次！")
                return
            self.board = board
            self.steps_count = 0
            self.solution_moves = []
            self.detailed_moves = []
            self.current_step = 0
            self.solved_initial_board = None
            self.set_control_buttons_state(False)
            self.update_board()
            self.display_solution_steps()
            self.update_preview(self.board)
            self.add_info(f"已加载新棋盘")
            self.status_label.configure(text="状态: 已加载", fg="#2ECC71")
            self.progress['value'] = 0
        except Exception as e:
            messagebox.showerror("错误", f"输入无效：{e}")
    
    def move_tile(self, i, j):
        if self.solving or self.auto_playing:
            return
        zero = self.board.index(0)
        zi, zj = zero//5, zero%5
        if abs(i-zi)+abs(j-zj) == 1:
            self.board[zero], self.board[i*5+j] = self.board[i*5+j], self.board[zero]
            self.steps_count += 1
            self.update_board()
            self.update_preview(self.board)
            self.solution_moves = []
            self.detailed_moves = []
            self.current_step = 0
            self.solved_initial_board = None
            self.set_control_buttons_state(False)
            self.display_solution_steps()
            self.status_label.configure(text="状态: 手动模式", fg="#F39C12")
            self.progress['value'] = 0
    
    def start_db_building(self):
        self.db_building = True
        self.status_label.configure(text="状态: 构建数据库中...", fg="#F39C12")
        self.progress.configure(mode='indeterminate')
        self.progress.start(10)
        def build_in_thread():
            try:
                self.db_manager = PatternDatabaseManager()
                self.db_manager.build_all_async(progress_callback=self.on_db_progress, max_workers=2)
                self.root.after(0, self.on_db_complete)
            except Exception as e:
                print(f"数据库构建错误: {e}")
                self.root.after(0, lambda: self.on_db_error(str(e)))
        threading.Thread(target=build_in_thread, daemon=True).start()
    
    def on_db_progress(self, completed, total, pattern):
        self.root.after(0, lambda: self._update_progress(completed, total))
    
    def _update_progress(self, completed, total):
        self.add_info(f"数据库构建进度: {completed}/{total}")
        self.status_label.configure(text=f"状态: 构建数据库 ({completed}/{total})", fg="#F39C12")
    
    def on_db_complete(self):
        self.db_building = False
        self.progress.stop()
        self.progress.configure(mode='determinate')
        self.progress['value'] = 0
        self.status_label.configure(text="状态: 就绪", fg="#2ECC71")
        self.add_info("✅ 所有模式数据库构建完成！内存使用正常")
    
    def on_db_error(self, error):
        self.db_building = False
        self.progress.stop()
        self.progress.configure(mode='determinate')
        self.status_label.configure(text="状态: 使用曼哈顿距离", fg="#E74C3C")
        self.add_info(f"❌ 数据库构建失败: {error}")
    
    def calc_inversion(self, board):
        inv = 0
        arr = [x for x in board if x != 0]
        for i in range(len(arr)):
            for j in range(i+1, len(arr)):
                if arr[i] > arr[j]:
                    inv += 1
        return inv
    
    def is_solvable(self, board):
        return self.calc_inversion(board) % 2 == 0
    
    def solve_puzzle(self):
        if self.solving:
            return
        if self.db_building:
            messagebox.showinfo("提示", "数据库还在构建中，请稍后再试...")
            return
        if self.board == list(range(1,25)) + [0]:
            messagebox.showinfo("提示", "已经是完成状态！")
            return
        if not self.is_solvable(self.board):
            inv = self.calc_inversion(self.board)
            messagebox.showerror("错误", f"当前棋盘无解！\n\n5x5拼图可解条件：逆序数为偶数\n当前逆序数：{inv}")
            return
        self.solving = True
        self.solve_btn.configure(state=tk.DISABLED, text="⏳ 求解中...")
        self.status_label.configure(text="状态: 求解中...", fg="#3498DB")
        self.progress.configure(mode='indeterminate')
        self.progress.start(10)
        self.add_info("开始求解（使用多数据库启发式）...")
        self.solved_initial_board = self.board[:]
        def solve_thread():
            try:
                solver = FastPuzzleSolver(self.board, db_manager=self.db_manager)
                moves, nodes = solver.solve(progress_callback=self.update_solve_progress)
                self.root.after(0, lambda: self.on_solve_complete(moves, nodes))
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.root.after(0, lambda: self.on_solve_complete(None, 0, error=str(e)))
        threading.Thread(target=solve_thread, daemon=True).start()
    
    def update_solve_progress(self, nodes, threshold, stack_depth):
        self.root.after(0, lambda: self._do_update_progress(nodes, threshold))
    
    def _do_update_progress(self, nodes, threshold):
        self.status_label.configure(text=f"状态: 求解中 (扩展{nodes:,}节点)", fg="#3498DB")
    
    def on_solve_complete(self, moves, nodes, error=None):
        self.progress.stop()
        self.progress.configure(mode='determinate')
        self.solving = False
        self.solve_btn.configure(state=tk.NORMAL, text="🔍 自动求解")
        if error:
            messagebox.showerror("错误", f"求解失败：{error}")
            self.status_label.configure(text="状态: 错误", fg="#E74C3C")
            self.add_info(f"❌ 求解失败：{error}")
            return
        if moves is None:
            messagebox.showerror("错误", "无法求解此拼图！")
            self.status_label.configure(text="状态: 无解", fg="#E74C3C")
            self.add_info("❌ 求解失败：未找到解法")
            return
        self.solution_moves = moves
        self.detailed_moves = self.generate_detailed_moves(self.solved_initial_board, moves)
        self.current_step = 0
        self.set_control_buttons_state(True)
        self.display_solution_steps()
        self.update_preview(self.solved_initial_board)
        messagebox.showinfo("求解成功", f"找到解法！\n步数: {len(moves)}\n扩展节点: {nodes:,}")
        self.status_label.configure(text=f"状态: 已求解 ({len(moves)}步)", fg="#2ECC71")
        self.add_info(f"✅ 求解成功！共 {len(moves)} 步，扩展 {nodes:,} 个节点")
        self.progress['maximum'] = len(moves)
        self.progress['value'] = 0
    
    def next_step(self):
        if self.solution_moves and self.current_step < len(self.solution_moves):
            self.execute_move(self.solution_moves[self.current_step])
            self.current_step += 1
            self.progress['value'] = self.current_step
            self.update_preview(self.board)
            self.steps_listbox.selection_clear(0, tk.END)
            if self.current_step > 0:
                self.steps_listbox.selection_set(self.current_step-1)
                self.steps_listbox.see(self.current_step-1)
            if self.current_step >= len(self.solution_moves):
                self.set_control_buttons_state(False)
                self.status_label.configure(text="状态: 已完成", fg="#2ECC71")
                self.add_info("🎉 所有步骤执行完毕！")
                if self.auto_playing:
                    self.stop_auto_play()
    
    def prev_step(self):
        if self.current_step > 0:
            original = self.get_initial_board()
            self.board = original[:]
            self.steps_count = 0
            for i in range(self.current_step-1):
                self.execute_move(self.solution_moves[i], update=False)
            self.current_step -= 1
            self.update_board()
            self.update_preview(self.board)
            self.progress['value'] = self.current_step
            self.steps_listbox.selection_clear(0, tk.END)
            if self.current_step > 0:
                self.steps_listbox.selection_set(self.current_step-1)
                self.steps_listbox.see(self.current_step-1)
            self.status_label.configure(text=f"状态: 回退到第{self.current_step}步", fg="#F39C12")
    
    def execute_move(self, move, update=True):
        zero = self.board.index(0)
        zi, zj = zero//5, zero%5
        if move == 'U' and zi>0:
            target = (zi-1)*5+zj
        elif move == 'D' and zi<4:
            target = (zi+1)*5+zj
        elif move == 'L' and zj>0:
            target = zi*5+(zj-1)
        elif move == 'R' and zj<4:
            target = zi*5+(zj+1)
        else:
            return False
        self.board[zero], self.board[target] = self.board[target], self.board[zero]
        self.steps_count += 1
        if update:
            self.update_board()
        return True
    
    def get_initial_board(self):
        if hasattr(self, 'solved_initial_board') and self.solved_initial_board:
            return self.solved_initial_board[:]
        return self.board[:]
    
    def auto_play(self):
        if self.auto_playing:
            return
        if not self.solution_moves or self.current_step >= len(self.solution_moves):
            messagebox.showinfo("提示", "请先求解！")
            return
        self.auto_playing = True
        self.auto_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.status_label.configure(text="状态: 自动播放中", fg="#E67E22")
        self.add_info("▶ 开始自动播放")
        self.play_next()
    
    def play_next(self):
        if self.auto_playing and self.current_step < len(self.solution_moves):
            self.next_step()
            self.root.after(400, self.play_next)
        elif self.current_step >= len(self.solution_moves):
            self.stop_auto_play()
    
    def stop_auto_play(self):
        self.auto_playing = False
        self.auto_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self.status_label.configure(text="状态: 已停止", fg="#F39C12")
        self.add_info("⏹ 停止自动播放")
    
    def reset_puzzle(self):
        if self.solving or self.auto_playing:
            return
        self.board = list(range(1,25)) + [0]
        self.steps_count = 0
        self.solution_moves = []
        self.detailed_moves = []
        self.current_step = 0
        self.solved_initial_board = None
        self.set_control_buttons_state(False)
        self.update_board()
        self.display_solution_steps()
        self.update_preview(self.board)
        self.status_label.configure(text="状态: 已重置", fg="#F39C12")
        self.progress['value'] = 0
        self.add_info("已重置棋盘")
    
    def shuffle_puzzle(self):
        if self.solving or self.auto_playing:
            return
        self.board = list(range(1,25)) + [0]
        moves_count = random.randint(100, 150)
        for _ in range(moves_count):
            zero = self.board.index(0)
            zi, zj = zero//5, zero%5
            possible = []
            if zi>0: possible.append('U')
            if zi<4: possible.append('D')
            if zj>0: possible.append('L')
            if zj<4: possible.append('R')
            if possible:
                move = random.choice(possible)
                if move == 'U': target = (zi-1)*5+zj
                elif move == 'D': target = (zi+1)*5+zj
                elif move == 'L': target = zi*5+(zj-1)
                else: target = zi*5+(zj+1)
                self.board[zero], self.board[target] = self.board[target], self.board[zero]
        self.steps_count = 0
        self.solution_moves = []
        self.detailed_moves = []
        self.current_step = 0
        self.solved_initial_board = None
        self.set_control_buttons_state(False)
        self.update_board()
        self.display_solution_steps()
        self.update_preview(self.board)
        self.status_label.configure(text="状态: 已打乱", fg="#F39C12")
        self.progress['value'] = 0
        inv = self.calc_inversion(self.board)
        self.add_info(f"🎲 已随机打乱棋盘（{moves_count}步），逆序数={inv}")
    
    def set_control_buttons_state(self, enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        self.prev_btn.configure(state=state)
        self.next_btn.configure(state=state)
        self.auto_btn.configure(state=state)
        if not enabled:
            self.stop_btn.configure(state=tk.DISABLED)
    
    def run(self):
        self.root.mainloop()


def main():
    multiprocessing.freeze_support()
    # 删除旧的错误缓存（如果存在）
    if os.path.exists("pdb_cache"):
        for f in os.listdir("pdb_cache"):
            if f.endswith(".bin"):
                path = os.path.join("pdb_cache", f)
                try:
                    with open(path, 'rb') as fp:
                        db = pickle.load(fp)
                    # 如果状态数超过100万，说明是错误版本，删除
                    if len(db) > 1000000:
                        os.remove(path)
                        print(f"删除错误缓存: {f}")
                except:
                    pass
    gui = SimplePuzzleGUI()
    gui.run()


if __name__ == "__main__":
    main()
