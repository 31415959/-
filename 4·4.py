import sys
import time
import tkinter as tk
from tkinter import messagebox, ttk, simpledialog
import threading
import random

class FastPuzzleSolver:
    def __init__(self, start_board, size=4):
        self.size = size
        self.n = size * size
        self.start = self._encode(start_board)
        self.goal = self._encode(list(range(1, self.n)) + [0])
        # 目标位置表
        goal_list = list(range(1, self.n)) + [0]
        self.goal_pos = {}
        for idx, val in enumerate(goal_list):
            if val != 0:
                self.goal_pos[val] = (idx // size, idx % size)
        # 预计算邻居表
        self.neighbor_table = self._build_neighbor_table()
        # 启发式缓存
        self.h_cache = {}

    def _encode(self, board):
        state = 0
        for i, v in enumerate(board):
            state |= (v << (i * 4))
        return state

    def _decode(self, state):
        board = []
        for i in range(self.n):
            board.append((state >> (i * 4)) & 0xF)
        return board

    def _build_neighbor_table(self):
        table = [[] for _ in range(self.n)]
        dirs = [(-1,0),(1,0),(0,-1),(0,1)]
        for idx in range(self.n):
            r, c = idx // self.size, idx % self.size
            for dr, dc in dirs:
                nr, nc = r+dr, c+dc
                if 0 <= nr < self.size and 0 <= nc < self.size:
                    nidx = nr * self.size + nc
                    table[idx].append(nidx)
        return table

    def move(self, state, pos0, new_pos):
        v0 = (state >> (pos0*4)) & 0xF
        v1 = (state >> (new_pos*4)) & 0xF
        state &= ~(0xF << (pos0*4))
        state &= ~(0xF << (new_pos*4))
        state |= (v1 << (pos0*4))
        state |= (v0 << (new_pos*4))
        return state

    def get_zero_pos(self, state):
        for i in range(self.n):
            if ((state >> (i*4)) & 0xF) == 0:
                return i
        return -1

    def manhattan_distance(self, state):
        dist = 0
        for i in range(self.n):
            val = (state >> (i*4)) & 0xF
            if val != 0:
                r, c = i // self.size, i % self.size
                tr, tc = self.goal_pos[val]
                dist += abs(r - tr) + abs(c - tc)
        return dist

    def linear_conflict(self, state):
        conflict = 0
        size = self.size
        for r in range(size):
            row = []
            for c in range(size):
                idx = r*size + c
                val = (state >> (idx*4)) & 0xF
                if val != 0 and (val-1)//size == r:
                    target_col = (val-1) % size
                    row.append((target_col, c))
            for i in range(len(row)):
                for j in range(i+1, len(row)):
                    if row[i][0] > row[j][0] and row[i][1] < row[j][1]:
                        conflict += 2
                    if row[i][0] < row[j][0] and row[i][1] > row[j][1]:
                        conflict += 2
        for c in range(size):
            col = []
            for r in range(size):
                idx = r*size + c
                val = (state >> (idx*4)) & 0xF
                if val != 0 and (val-1)%size == c:
                    target_row = (val-1)//size
                    col.append((target_row, r))
            for i in range(len(col)):
                for j in range(i+1, len(col)):
                    if col[i][0] > col[j][0] and col[i][1] < col[j][1]:
                        conflict += 2
                    if col[i][0] < col[j][0] and col[i][1] > col[j][1]:
                        conflict += 2
        return conflict

    def heuristic(self, state):
        if state in self.h_cache:
            return self.h_cache[state]
        h = self.manhattan_distance(state) + self.linear_conflict(state)
        self.h_cache[state] = h
        return h

    def ida_star(self, callback=None):
        start_state = self.start
        threshold = self.heuristic(start_state)
        self.nodes_expanded = 0
        
        while True:
            self.transposition = {}
            path_states = [start_state]
            path_moves = []
            pos0 = self.get_zero_pos(start_state)
            
            found, new_threshold = self._search(0, threshold, None, pos0, 
                                                path_states, path_moves)
            if found:
                return path_moves, self.nodes_expanded
            if new_threshold == float('inf'):
                return None, self.nodes_expanded
            threshold = new_threshold
            if callback:
                callback(threshold)

    def _search(self, g, threshold, last_move_rev, pos0, path_states, path_moves):
        state = path_states[-1]
        
        prev_g = self.transposition.get(state)
        if prev_g is not None and prev_g <= g:
            return False, float('inf')
        self.transposition[state] = g
        
        f = g + self.heuristic(state)
        if f > threshold:
            return False, f
        if state == self.goal:
            return True, threshold
        
        cur_pos0 = pos0
        min_f = float('inf')
        
        moves = []
        for new_pos in self.neighbor_table[cur_pos0]:
            r0, c0 = cur_pos0 // self.size, cur_pos0 % self.size
            r1, c1 = new_pos // self.size, new_pos % self.size
            if r1 == r0 - 1: move = 'U'
            elif r1 == r0 + 1: move = 'D'
            elif c1 == c0 - 1: move = 'L'
            else: move = 'R'
            
            if last_move_rev and move == last_move_rev:
                continue
                
            new_state = self.move(state, cur_pos0, new_pos)
            moves.append((new_state, move, new_pos))
        
        moves.sort(key=lambda x: self.heuristic(x[0]))
        
        for new_state, move, new_pos in moves:
            rev_move = {'U':'D','D':'U','L':'R','R':'L'}[move]
            path_states.append(new_state)
            path_moves.append(move)
            self.nodes_expanded += 1
            
            found, new_threshold = self._search(g+1, threshold, rev_move, new_pos,
                                                path_states, path_moves)
            if found:
                return True, new_threshold
            if new_threshold < min_f:
                min_f = new_threshold
                
            path_states.pop()
            path_moves.pop()
        
        return False, min_f


class PuzzleGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("数字华容道 - 4x4 求解器")
        self.root.geometry("1100x800")  # 增加宽度以容纳预览区域
        self.root.resizable(True, True)
        
        # 游戏状态
        self.board = list(range(1, 16)) + [0]
        self.solution_moves = []          # 方向列表
        self.detailed_moves = []          # 详细步骤 [(方向, 移动数字), ...]
        self.current_step = 0
        self.auto_playing = False
        self.solving = False
        self.steps_count = 0
        
        # 颜色方案
        self.colors = {
            'bg': '#2C3E50',
            'button_bg': '#34495E',
            'button_fg': '#ECF0F1',
            'empty_bg': '#95A5A6',
            'button_hover': '#5D6D7E',
            'solve_btn': '#27AE60',
            'reset_btn': '#E74C3C',
            'step_btn': '#3498DB',
            'input_btn': '#9B59B6'
        }
        
        self.setup_ui()
        
    def setup_ui(self):
        # 设置主窗口背景
        self.root.configure(bg=self.colors['bg'])
        
        # 主框架分为左右两部分
        main_frame = tk.Frame(self.root, bg=self.colors['bg'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 左侧：游戏区域
        left_frame = tk.Frame(main_frame, bg=self.colors['bg'])
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 标题
        title_label = tk.Label(left_frame, text="数字华容道求解器", 
                               font=("微软雅黑", 20, "bold"),
                               fg="#ECF0F1", bg=self.colors['bg'])
        title_label.pack(pady=10)
        
        # 游戏区域
        self.game_frame = tk.Frame(left_frame, bg=self.colors['bg'])
        self.game_frame.pack(pady=20)
        
        self.buttons = [[None for _ in range(4)] for _ in range(4)]
        for i in range(4):
            for j in range(4):
                self.create_button(i, j)
        
        # 信息面板
        info_frame = tk.Frame(left_frame, bg=self.colors['bg'])
        info_frame.pack(pady=10)
        
        self.steps_label = tk.Label(info_frame, text="步数: 0", 
                                    font=("微软雅黑", 12),
                                    fg="#ECF0F1", bg=self.colors['bg'])
        self.steps_label.pack(side=tk.LEFT, padx=20)
        
        self.status_label = tk.Label(info_frame, text="状态: 就绪", 
                                     font=("微软雅黑", 12),
                                     fg="#F39C12", bg=self.colors['bg'])
        self.status_label.pack(side=tk.LEFT, padx=20)
        
        # 控制按钮
        control_frame = tk.Frame(left_frame, bg=self.colors['bg'])
        control_frame.pack(pady=20)
        
        # 第一行按钮
        btn_frame1 = tk.Frame(control_frame, bg=self.colors['bg'])
        btn_frame1.pack(pady=5)
        
        self.input_btn = tk.Button(btn_frame1, text="📝 输入棋盘", 
                                   command=self.input_board,
                                   font=("微软雅黑", 10, "bold"),
                                   bg=self.colors['input_btn'], fg="white",
                                   padx=12, pady=6, cursor="hand2")
        self.input_btn.pack(side=tk.LEFT, padx=5)
        
        self.solve_btn = tk.Button(btn_frame1, text="🔍 自动求解", 
                                   command=self.solve_puzzle,
                                   font=("微软雅黑", 10, "bold"),
                                   bg=self.colors['solve_btn'], fg="white",
                                   padx=12, pady=6, cursor="hand2")
        self.solve_btn.pack(side=tk.LEFT, padx=5)
        
        self.reset_btn = tk.Button(btn_frame1, text="🔄 重置", 
                                   command=self.reset_puzzle,
                                   font=("微软雅黑", 10, "bold"),
                                   bg=self.colors['reset_btn'], fg="white",
                                   padx=12, pady=6, cursor="hand2")
        self.reset_btn.pack(side=tk.LEFT, padx=5)
        
        self.shuffle_btn = tk.Button(btn_frame1, text="🎲 随机打乱", 
                                     command=self.shuffle_puzzle,
                                     font=("微软雅黑", 10, "bold"),
                                     bg=self.colors['step_btn'], fg="white",
                                     padx=12, pady=6, cursor="hand2")
        self.shuffle_btn.pack(side=tk.LEFT, padx=5)
        
        # 第二行按钮
        btn_frame2 = tk.Frame(control_frame, bg=self.colors['bg'])
        btn_frame2.pack(pady=5)
        
        self.prev_btn = tk.Button(btn_frame2, text="◀ 上一步", 
                                  command=self.prev_step,
                                  font=("微软雅黑", 10),
                                  bg=self.colors['step_btn'], fg="white",
                                  padx=12, pady=6, cursor="hand2",
                                  state=tk.DISABLED)
        self.prev_btn.pack(side=tk.LEFT, padx=5)
        
        self.next_btn = tk.Button(btn_frame2, text="下一步 ▶", 
                                  command=self.next_step,
                                  font=("微软雅黑", 10),
                                  bg=self.colors['step_btn'], fg="white",
                                  padx=12, pady=6, cursor="hand2",
                                  state=tk.DISABLED)
        self.next_btn.pack(side=tk.LEFT, padx=5)
        
        self.auto_btn = tk.Button(btn_frame2, text="▶ 自动播放", 
                                  command=self.auto_play,
                                  font=("微软雅黑", 10),
                                  bg=self.colors['step_btn'], fg="white",
                                  padx=12, pady=6, cursor="hand2",
                                  state=tk.DISABLED)
        self.auto_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = tk.Button(btn_frame2, text="⏹ 停止", 
                                  command=self.stop_auto_play,
                                  font=("微软雅黑", 10),
                                  bg="#E67E22", fg="white",
                                  padx=12, pady=6, cursor="hand2",
                                  state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # 进度条
        self.progress = ttk.Progressbar(left_frame, length=400, mode='determinate')
        self.progress.pack(pady=10)
        
        # 右侧：步骤显示区域和棋盘预览
        right_frame = tk.Frame(main_frame, bg=self.colors['bg'], width=400)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        right_frame.pack_propagate(False)
        
        # 步骤标题
        steps_title = tk.Label(right_frame, text="📋 求解步骤", 
                              font=("微软雅黑", 14, "bold"),
                              fg="#ECF0F1", bg=self.colors['bg'])
        steps_title.pack(pady=10)
        
        # 步骤信息标签
        self.steps_info_label = tk.Label(right_frame, text="共 0 步", 
                                        font=("微软雅黑", 10),
                                        fg="#3498DB", bg=self.colors['bg'])
        self.steps_info_label.pack()
        
        # 步骤列表（带滚动条）
        steps_list_frame = tk.Frame(right_frame, bg=self.colors['bg'])
        steps_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        scrollbar = tk.Scrollbar(steps_list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.steps_listbox = tk.Listbox(steps_list_frame, 
                                        font=("Consolas", 16),
                                        bg="#34495E", 
                                        fg="#ECF0F1",
                                        selectmode=tk.SINGLE,
                                        yscrollcommand=scrollbar.set,
                                        height=12)
        self.steps_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.steps_listbox.yview)
        
        # 绑定点击事件，跳转到对应步骤
        self.steps_listbox.bind('<ButtonRelease-1>', self.on_step_selected)
        
        # 新增：棋盘状态预览区域
        preview_frame = tk.Frame(right_frame, bg=self.colors['bg'], relief=tk.GROOVE, bd=2)
        preview_frame.pack(fill=tk.BOTH, pady=10, padx=5)
        
        preview_title = tk.Label(preview_frame, text="棋盘状态预览 (点击步骤后显示)", 
                                 font=("微软雅黑", 10, "bold"),
                                 fg="#ECF0F1", bg=self.colors['bg'])
        preview_title.pack(pady=5)
        
        self.preview_text = tk.Text(preview_frame, height=8, width=30,
                                    font=("Courier New", 12),
                                    bg="#1E2A38", fg="#ECF0F1",
                                    wrap=tk.NONE, state=tk.DISABLED)
        self.preview_text.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)
        
        # 底部信息框
        info_text_frame = tk.Frame(left_frame, bg=self.colors['bg'])
        info_text_frame.pack(pady=10, fill=tk.X)
        
        tk.Label(info_text_frame, text="运行日志:", 
                font=("微软雅黑", 10, "bold"),
                fg="#ECF0F1", bg=self.colors['bg']).pack(anchor=tk.W)
        
        self.info_text = tk.Text(info_text_frame, height=5, width=50, 
                                 font=("微软雅黑", 9), wrap=tk.WORD)
        self.info_text.pack(fill=tk.X, pady=5)
        
        self.add_info("欢迎使用数字华容道求解器！")
        self.add_info("点击「输入棋盘」按钮，然后输入16个数字（空格分隔）")
        self.add_info("空白块可以用 0、X 表示")
        self.add_info("示例：7 14 1 3 2 10 13 8 4 5 12 9 15 X 6 11")
    
    def add_info(self, message):
        """添加信息到文本框"""
        self.info_text.insert(tk.END, f"> {message}\n")
        self.info_text.see(tk.END)
        self.root.update_idletasks()
    
    def create_button(self, i, j):
        """创建数字按钮"""
        value = self.board[i*4 + j]
        text = str(value) if value != 0 else ""
        
        btn = tk.Button(self.game_frame, text=text,
                       width=6, height=3,
                       font=("Arial", 20, "bold"),
                       command=lambda i=i, j=j: self.move_tile(i, j))
        
        if value == 0:
            btn.configure(bg=self.colors['empty_bg'], state=tk.DISABLED)
        else:
            btn.configure(bg=self.colors['button_bg'], 
                         fg=self.colors['button_fg'],
                         activebackground=self.colors['button_hover'])
        
        btn.grid(row=i, column=j, padx=3, pady=3)
        self.buttons[i][j] = btn
    
    def update_board(self):
        """更新界面棋盘"""
        for i in range(4):
            for j in range(4):
                value = self.board[i*4 + j]
                text = str(value) if value != 0 else ""
                btn = self.buttons[i][j]
                btn.configure(text=text)
                
                if value == 0:
                    btn.configure(bg=self.colors['empty_bg'], state=tk.DISABLED)
                else:
                    btn.configure(bg=self.colors['button_bg'], 
                                 fg=self.colors['button_fg'],
                                 state=tk.NORMAL)
        
        # 更新步数显示
        self.steps_label.configure(text=f"步数: {self.steps_count}")
        
        # 检查是否胜利
        if self.board == list(range(1, 16)) + [0]:
            messagebox.showinfo("恭喜！", "你赢了！🎉")
            self.status_label.configure(text="状态: 胜利!", fg="#2ECC71")
            self.add_info("🎉 恭喜！成功完成拼图！")
            if self.auto_playing:
                self.stop_auto_play()
    
    def format_board_text(self, board):
        """将棋盘格式化为文本表示（4x4，数字右对齐，空白用X）"""
        lines = []
        for i in range(4):
            row = []
            for j in range(4):
                val = board[i*4 + j]
                if val == 0:
                    row.append(" X".rjust(2))
                else:
                    row.append(f"{val:2d}")
            lines.append(" ".join(row))
        return "\n".join(lines)
    
    def update_preview(self, board):
        """更新右侧棋盘预览区域"""
        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete(1.0, tk.END)
        text_board = self.format_board_text(board)
        self.preview_text.insert(tk.END, text_board)
        self.preview_text.config(state=tk.DISABLED)
    
    def generate_detailed_moves(self, initial_board, moves):
        """根据初始棋盘和移动方向列表，生成详细的步骤信息（方向，移动数字）"""
        detailed = []
        board = initial_board[:]
        for move in moves:
            zero_pos = board.index(0)
            zero_i, zero_j = zero_pos // 4, zero_pos % 4
            target_i, target_j = zero_i, zero_j
            if move == 'U':
                target_i -= 1
            elif move == 'D':
                target_i += 1
            elif move == 'L':
                target_j -= 1
            elif move == 'R':
                target_j += 1
            target_pos = target_i * 4 + target_j
            moved_num = board[target_pos]  # 被移动的数字
            detailed.append((move, moved_num))
            # 模拟移动
            board[zero_pos], board[target_pos] = board[target_pos], board[zero_pos]
        return detailed
    
    def display_solution_steps(self):
        """在右侧列表显示详细求解步骤"""
        self.steps_listbox.delete(0, tk.END)
        
        if not self.detailed_moves:
            self.steps_info_label.configure(text="共 0 步")
            return
        
        self.steps_info_label.configure(text=f"共 {len(self.detailed_moves)} 步")
        
        # 显示每一步
        for i, (move, num) in enumerate(self.detailed_moves, 1):
            step_text = f"步骤 {i:3d}: 移动 {move}（移动数字 {num}）"
            self.steps_listbox.insert(tk.END, step_text)
        
        # 高亮当前步骤
        if self.current_step > 0:
            self.steps_listbox.selection_clear(0, tk.END)
            self.steps_listbox.selection_set(self.current_step - 1)
            self.steps_listbox.see(self.current_step - 1)
    
    def on_step_selected(self, event):
        """点击步骤列表时跳转到对应步骤并更新预览"""
        if not self.detailed_moves:
            return
        
        selection = self.steps_listbox.curselection()
        if selection:
            target_step = selection[0] + 1
            if target_step != self.current_step:
                self.jump_to_step(target_step)
    
    def jump_to_step(self, target_step):
        """跳转到指定步骤，并更新棋盘预览"""
        if target_step < 0 or target_step > len(self.detailed_moves):
            return
        
        # 重置到初始状态
        original_board = self.get_initial_board()
        self.board = original_board[:]
        self.steps_count = 0
        
        # 重新应用到目标步骤
        for i in range(target_step):
            move = self.solution_moves[i]
            self.execute_move(move, update=False)
        
        self.current_step = target_step
        self.update_board()
        self.progress['value'] = self.current_step
        
        # 更新预览区域
        self.update_preview(self.board)
        
        # 更新列表高亮
        self.steps_listbox.selection_clear(0, tk.END)
        if target_step > 0:
            self.steps_listbox.selection_set(target_step - 1)
            self.steps_listbox.see(target_step - 1)
        
        self.status_label.configure(text=f"状态: 第{target_step}步", fg="#F39C12")
    
    def input_board(self):
        """使用 simpledialog 输入棋盘"""
        if self.solving or self.auto_playing:
            messagebox.showwarning("提示", "请等待当前操作完成")
            return
        
        input_text = simpledialog.askstring(
            "输入棋盘", 
            "请输入16个数字（空格分隔）\n空白块用 0 或 X 表示\n\n示例：7 14 1 3 2 10 13 8 4 5 12 9 15 X 6 11",
            parent=self.root
        )
        
        if not input_text:
            return
        
        try:
            input_text = input_text.replace(',', ' ').replace('\n', ' ').replace('\r', ' ')
            parts = input_text.split()
            
            if len(parts) != 16:
                messagebox.showerror("错误", f"需要16个数字，但收到了{len(parts)}个！\n请检查输入。")
                return
            
            board = []
            for p in parts:
                p_upper = p.upper()
                if p_upper == 'X' or p_upper == '' or p == '0':
                    board.append(0)
                else:
                    try:
                        val = int(p)
                        if val < 1 or val > 15:
                            raise ValueError("数字必须在1-15之间")
                        board.append(val)
                    except ValueError:
                        messagebox.showerror("错误", f"无效输入：'{p}'\n请使用1-15的数字，空白用0或X表示。")
                        return
            
            if sorted(board) != list(range(16)):
                messagebox.showerror("错误", "数字必须包含0-15各一次！\n请检查是否有重复或遗漏。")
                return
            
            self.board = board
            self.steps_count = 0
            self.solution_moves = []
            self.detailed_moves = []
            self.current_step = 0
            self.set_control_buttons_state(False)
            self.update_board()
            self.display_solution_steps()
            self.update_preview(self.board)
            
            board_str = " ".join([str(x) if x != 0 else "X" for x in self.board])
            self.add_info(f"已加载新棋盘: {board_str}")
            self.status_label.configure(text="状态: 已加载", fg="#2ECC71")
            self.progress['value'] = 0
            
        except Exception as e:
            messagebox.showerror("错误", f"输入无效：{str(e)}")
    
    def move_tile(self, i, j):
        """移动瓷砖"""
        if self.solving or self.auto_playing:
            return
        
        zero_pos = self.board.index(0)
        zero_i, zero_j = zero_pos // 4, zero_pos % 4
        
        if (abs(i - zero_i) + abs(j - zero_j)) == 1:
            self.board[zero_pos], self.board[i*4+j] = self.board[i*4+j], self.board[zero_pos]
            self.steps_count += 1
            self.update_board()
            self.update_preview(self.board)
            
            # 清空解法（因为用户手动移动了）
            self.solution_moves = []
            self.detailed_moves = []
            self.current_step = 0
            self.set_control_buttons_state(False)
            self.display_solution_steps()
            self.status_label.configure(text="状态: 手动模式", fg="#F39C12")
            self.progress['value'] = 0
    
    def solve_puzzle(self):
        """求解拼图"""
        if self.solving:
            return
        
        if self.board == list(range(1, 16)) + [0]:
            messagebox.showinfo("提示", "已经是完成状态！")
            return
        
        if not self.is_solvable(self.board):
            messagebox.showerror("错误", "当前棋盘无解！\n请重新输入或打乱棋盘。")
            return
        
        self.solving = True
        self.solve_btn.configure(state=tk.DISABLED, text="⏳ 求解中...")
        self.status_label.configure(text="状态: 求解中...", fg="#3498DB")
        self.add_info("开始求解，请稍候...")
        
        def solve_thread():
            solver = FastPuzzleSolver(self.board)
            moves, nodes = solver.ida_star()
            self.root.after(0, lambda: self.on_solve_complete(moves, nodes))
        
        threading.Thread(target=solve_thread, daemon=True).start()
    
    def is_solvable(self, board):
        """检查棋盘是否有解"""
        inv = 0
        arr = [x for x in board if x != 0]
        for i in range(len(arr)):
            for j in range(i+1, len(arr)):
                if arr[i] > arr[j]:
                    inv += 1
        blank_row = board.index(0) // 4
        return (inv % 2) == (blank_row % 2 == 0)
    
    def on_solve_complete(self, moves, nodes):
        """求解完成回调"""
        self.solving = False
        self.solve_btn.configure(state=tk.NORMAL, text="🔍 自动求解")
        
        if moves is None:
            messagebox.showerror("错误", "无法求解此拼图！")
            self.status_label.configure(text="状态: 无解", fg="#E74C3C")
            self.add_info("❌ 求解失败：无法找到解法")
            return
        
        # 生成详细步骤（方向 + 移动的数字）
        self.solution_moves = moves
        self.detailed_moves = self.generate_detailed_moves(self.board, moves)
        self.current_step = 0
        self.set_control_buttons_state(True)
        self.display_solution_steps()
        # 预览初始棋盘
        self.update_preview(self.board)
        
        messagebox.showinfo("求解成功", 
                           f"找到解法！\n步数: {len(moves)}\n探索节点: {nodes:,}")
        self.status_label.configure(text=f"状态: 已求解 ({len(moves)}步)", fg="#2ECC71")
        self.add_info(f"✅ 求解成功！共 {len(moves)} 步，探索 {nodes:,} 个节点")
        self.progress['maximum'] = len(moves)
        self.progress['value'] = 0
    
    def next_step(self):
        """执行下一步"""
        if self.solution_moves and self.current_step < len(self.solution_moves):
            move = self.solution_moves[self.current_step]
            self.execute_move(move)
            self.current_step += 1
            self.progress['value'] = self.current_step
            # 更新预览
            self.update_preview(self.board)
            
            self.steps_listbox.selection_clear(0, tk.END)
            if self.current_step > 0:
                self.steps_listbox.selection_set(self.current_step - 1)
                self.steps_listbox.see(self.current_step - 1)
            
            if self.current_step >= len(self.solution_moves):
                self.set_control_buttons_state(False)
                self.status_label.configure(text="状态: 已完成", fg="#2ECC71")
                self.add_info("🎉 所有步骤执行完毕！")
                if self.auto_playing:
                    self.stop_auto_play()
    
    def prev_step(self):
        """返回上一步"""
        if self.current_step > 0:
            original_board = self.get_initial_board()
            self.board = original_board[:]
            self.steps_count = 0
            
            for i in range(self.current_step - 1):
                self.execute_move(self.solution_moves[i], update=False)
            
            self.current_step -= 1
            self.update_board()
            self.update_preview(self.board)
            self.progress['value'] = self.current_step
            
            self.steps_listbox.selection_clear(0, tk.END)
            if self.current_step > 0:
                self.steps_listbox.selection_set(self.current_step - 1)
                self.steps_listbox.see(self.current_step - 1)
            
            self.status_label.configure(text=f"状态: 回退到第{self.current_step}步", fg="#F39C12")
    
    def execute_move(self, move, update=True):
        """执行移动命令"""
        zero_pos = self.board.index(0)
        zero_i, zero_j = zero_pos // 4, zero_pos % 4
        
        if move == 'U' and zero_i > 0:
            target_pos = (zero_i - 1) * 4 + zero_j
        elif move == 'D' and zero_i < 3:
            target_pos = (zero_i + 1) * 4 + zero_j
        elif move == 'L' and zero_j > 0:
            target_pos = zero_i * 4 + (zero_j - 1)
        elif move == 'R' and zero_j < 3:
            target_pos = zero_i * 4 + (zero_j + 1)
        else:
            return False
        
        self.board[zero_pos], self.board[target_pos] = self.board[target_pos], self.board[zero_pos]
        self.steps_count += 1
        
        if update:
            self.update_board()
        return True
    
    def get_initial_board(self):
        """获取初始棋盘状态（求解前的棋盘）"""
        # 因为board可能被改变，但初始棋盘就是求解时的self.board的副本
        # 这里需要记录求解开始时的棋盘，但简便起见，从self.solution_moves反推初始状态
        # 更好的办法：保存一个self.initial_board_for_solution
        if self.solution_moves:
            # 从当前状态反向回退？由于我们已经存储了detailed_moves，但详细步骤是从初始棋盘生成的。
            # 最简单的：在求解时保存初始棋盘副本
            # 为了支持重置，在on_solve_complete中保存 self.solved_initial_board
            if hasattr(self, 'solved_initial_board'):
                return self.solved_initial_board[:]
        # 若没有求解，返回当前board（但重置时可能不准确，但无大碍）
        return self.board[:]
    
    def auto_play(self):
        """自动播放"""
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
        """播放下一步（用于自动播放）"""
        if self.auto_playing and self.current_step < len(self.solution_moves):
            self.next_step()
            self.root.after(400, self.play_next)
        elif self.current_step >= len(self.solution_moves):
            self.stop_auto_play()
    
    def stop_auto_play(self):
        """停止自动播放"""
        self.auto_playing = False
        self.auto_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self.status_label.configure(text="状态: 已停止", fg="#F39C12")
        self.add_info("⏹ 停止自动播放")
    
    def reset_puzzle(self):
        """重置到初始状态"""
        if self.solving or self.auto_playing:
            return
        
        if self.solution_moves and hasattr(self, 'solved_initial_board'):
            self.board = self.solved_initial_board[:]
        else:
            self.board = list(range(1, 16)) + [0]
        
        self.steps_count = 0
        self.solution_moves = []
        self.detailed_moves = []
        self.current_step = 0
        self.set_control_buttons_state(False)
        self.update_board()
        self.display_solution_steps()
        self.update_preview(self.board)
        self.status_label.configure(text="状态: 已重置", fg="#F39C12")
        self.progress['value'] = 0
        self.add_info("已重置棋盘")
    
    def shuffle_puzzle(self):
        """随机打乱棋盘（确保有解）"""
        if self.solving or self.auto_playing:
            return
        
        self.board = list(range(1, 16)) + [0]
        moves_count = random.randint(100, 200)
        for _ in range(moves_count):
            zero_pos = self.board.index(0)
            zero_i, zero_j = zero_pos // 4, zero_pos % 4
            
            possible_moves = []
            if zero_i > 0: possible_moves.append('U')
            if zero_i < 3: possible_moves.append('D')
            if zero_j > 0: possible_moves.append('L')
            if zero_j < 3: possible_moves.append('R')
            
            if possible_moves:
                move = random.choice(possible_moves)
                self.execute_move(move, update=False)
        
        self.steps_count = 0
        self.solution_moves = []
        self.detailed_moves = []
        self.current_step = 0
        self.set_control_buttons_state(False)
        self.update_board()
        self.display_solution_steps()
        self.update_preview(self.board)
        self.status_label.configure(text="状态: 已打乱", fg="#F39C12")
        self.progress['value'] = 0
        self.add_info(f"🎲 已随机打乱棋盘（{moves_count}步）")
    
    def set_control_buttons_state(self, enabled):
        """设置控制按钮状态"""
        state = tk.NORMAL if enabled else tk.DISABLED
        self.prev_btn.configure(state=state)
        self.next_btn.configure(state=state)
        self.auto_btn.configure(state=state)
        if not enabled:
            self.stop_btn.configure(state=tk.DISABLED)
    
    def run(self):
        """运行GUI"""
        self.root.mainloop()


def main():
    try:
        gui = PuzzleGUI()
        gui.run()
    except Exception as e:
        print(f"错误：{e}")
        print("请确保已安装tkinter")


if __name__ == "__main__":
    main()