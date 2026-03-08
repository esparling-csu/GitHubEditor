import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.simpledialog as simpledialog

from SecretsFile.PasswordManager import PasswordManager
from github_client import GitHubClient, GitHubApiError


PM = PasswordManager()


def get_github_token():
    try:
        note = PM.get_note('GitGub_work')
        if not note or len(note) < 2:
            return None
        token = (note[1] or '').strip()
        return token or None
    except Exception:
        return None


class GitHubEditorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('GitHub GUI Editor')
        self.geometry('1200x750')

        self.client = None
        self.user = None

        self.selected_repo = None  # dict
        self.selected_owner = None
        self.selected_repo_name = None

        self.branch_var = tk.StringVar(value='')
        self.repo_filter_var = tk.StringVar(value='')

        self._build_ui()
        self._startup_auth_and_load()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        main = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main.grid(row=0, column=0, sticky='nsew')

        left = ttk.Frame(main)
        right = ttk.Frame(main)
        main.add(left, weight=1)
        main.add(right, weight=3)

        # Left: repos
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)

        ttk.Label(left, text='Repos').grid(row=0, column=0, sticky='w', padx=8, pady=(8, 2))

        filter_frame = ttk.Frame(left)
        filter_frame.grid(row=1, column=0, sticky='ew', padx=8)
        filter_frame.columnconfigure(0, weight=1)

        repo_filter = ttk.Entry(filter_frame, textvariable=self.repo_filter_var)
        repo_filter.grid(row=0, column=0, sticky='ew')
        repo_filter.bind('<KeyRelease>', lambda e: self._apply_repo_filter())

        ttk.Button(filter_frame, text='Refresh', command=self.refresh_repos).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(filter_frame, text='Create', command=self.create_repo_dialog).grid(row=0, column=2, padx=(6, 0))

        self.repos_list = tk.Listbox(left, exportselection=False)
        self.repos_list.grid(row=2, column=0, sticky='nsew', padx=8, pady=8)
        self.repos_list.bind('<<ListboxSelect>>', self._on_repo_selected)

        # Right: branch, file tree, preview, actions
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        topbar = ttk.Frame(right)
        topbar.grid(row=0, column=0, sticky='ew', padx=8, pady=(8, 2))
        topbar.columnconfigure(1, weight=1)

        self.user_label = ttk.Label(topbar, text='Not logged in')
        self.user_label.grid(row=0, column=0, sticky='w')

        ttk.Label(topbar, text='Branch:').grid(row=0, column=1, sticky='e', padx=(10, 4))
        self.branch_entry = ttk.Entry(topbar, textvariable=self.branch_var, width=22)
        self.branch_entry.grid(row=0, column=2, sticky='w')
        ttk.Button(topbar, text='Load', command=self.load_repo_root).grid(row=0, column=3, padx=(6, 0))

        actions = ttk.Frame(right)
        actions.grid(row=1, column=0, sticky='ew', padx=8, pady=(2, 8))

        ttk.Button(actions, text='Upload File(s)', command=self.upload_files_dialog).pack(side=tk.LEFT)
        ttk.Button(actions, text='Delete Selected', command=self.delete_selected_dialog).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text='Download Selected', command=self.download_selected_dialog).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text='Copy Path', command=self.copy_selected_path).pack(side=tk.LEFT, padx=(8, 0))

        splitter = ttk.PanedWindow(right, orient=tk.HORIZONTAL)
        splitter.grid(row=2, column=0, sticky='nsew', padx=8, pady=(0, 8))

        tree_frame = ttk.Frame(splitter)
        preview_frame = ttk.Frame(splitter)
        splitter.add(tree_frame, weight=2)
        splitter.add(preview_frame, weight=3)

        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(tree_frame, columns=('type',), show='tree')
        self.tree.grid(row=0, column=0, sticky='nsew')
        self.tree.bind('<<TreeviewSelect>>', self._on_tree_selected)
        self.tree.bind('<<TreeviewOpen>>', self._on_tree_open)

        yscroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        yscroll.grid(row=0, column=1, sticky='ns')
        self.tree.configure(yscrollcommand=yscroll.set)

        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(1, weight=1)

        ttk.Label(preview_frame, text='Preview').grid(row=0, column=0, sticky='w')
        self.preview_text = tk.Text(preview_frame, wrap='none')
        self.preview_text.grid(row=1, column=0, sticky='nsew')
        self.preview_text.configure(state='disabled')

        bottom = ttk.Frame(right)
        bottom.grid(row=3, column=0, sticky='ew', padx=8, pady=(0, 8))
        bottom.columnconfigure(0, weight=1)

        ttk.Label(bottom, text='Log').grid(row=0, column=0, sticky='w')
        self.log_text = tk.Text(bottom, height=6, wrap='word')
        self.log_text.grid(row=1, column=0, sticky='ew')
        self.log_text.configure(state='disabled')

    def log(self, msg):
        self.log_text.configure(state='normal')
        self.log_text.insert('end', msg + '\n')
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def _startup_auth_and_load(self):
        token = get_github_token()
        if not token:
            token = self._prompt_for_token_and_save()

        if not token:
            self.user_label.configure(text='Token missing. App cannot continue.')
            self.log('No GitHub token available.')
            return

        try:
            self.client = GitHubClient(token)
            self.user = self.client.get_user()
            self.user_label.configure(text=f"Logged in as: {self.user.get('login', '')}")
            self.log('Authenticated successfully.')
            self.refresh_repos()
        except Exception as e:
            self.user_label.configure(text='Login failed')
            self.log(f'Login failed: {e}')
            messagebox.showerror('Login failed', str(e))

    def _prompt_for_token_and_save(self):
        dlg = tk.Toplevel(self)
        dlg.title('GitHub Token')
        dlg.geometry('520x190')
        dlg.transient(self)
        dlg.grab_set()

        ttk.Label(dlg, text="Paste GitHub Personal Access Token (PAT):").pack(anchor='w', padx=10, pady=(10, 4))
        token_var = tk.StringVar(value='')
        entry = ttk.Entry(dlg, textvariable=token_var, show='*')
        entry.pack(fill='x', padx=10)
        entry.focus_set()

        ttk.Label(dlg, text="It will be stored encrypted via PasswordManager under key 'GitHub_work'.").pack(anchor='w', padx=10, pady=(6, 4))

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill='x', padx=10, pady=10)

        result = {'token': None}

        def save_and_close():
            t = token_var.get().strip()
            if not t:
                messagebox.showwarning('Token required', 'Token cannot be blank.')
                return
            try:
                PM.add_user_note('GitHub_work', self.user.get('login', '') if self.user else 'github', t)
            except Exception:
                # If add_user_note fails for any reason, fall back to raw file storage is not desirable.
                # We keep it simple: show error.
                messagebox.showerror('Save failed', 'Could not save token using PasswordManager.')
                return
            result['token'] = t
            dlg.destroy()

        def cancel():
            dlg.destroy()

        ttk.Button(btn_frame, text='Save', command=save_and_close).pack(side='left')
        ttk.Button(btn_frame, text='Cancel', command=cancel).pack(side='left', padx=(8, 0))

        self.wait_window(dlg)
        return result['token']

    def refresh_repos(self):
        if not self.client:
            return
        self.log('Loading repos...')

        def work():
            try:
                repos = self.client.list_repos()
                self._all_repos = repos
                self.after(0, self._render_repo_list)
                self.after(0, lambda: self.log(f"Loaded {len(repos)} repos."))
            except Exception as e:
                self.after(0, lambda: self.log(f'Repo load failed: {e}'))
                self.after(0, lambda: messagebox.showerror('Repo load failed', str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _render_repo_list(self):
        self.repos_list.delete(0, 'end')
        self._filtered_repos = self._filter_repos(self.repo_filter_var.get())
        for r in self._filtered_repos:
            full = r.get('full_name', '')
            self.repos_list.insert('end', full)

    def _filter_repos(self, text):
        if not getattr(self, '_all_repos', None):
            return []
        t = (text or '').strip().lower()
        if not t:
            return list(self._all_repos)
        out = []
        for r in self._all_repos:
            name = (r.get('full_name', '') or '').lower()
            if t in name:
                out.append(r)
        return out

    def _apply_repo_filter(self):
        self._render_repo_list()

    def _on_repo_selected(self, _evt):
        sel = self.repos_list.curselection()
        if not sel:
            return
        idx = int(sel[0])
        repo = self._filtered_repos[idx]
        self.selected_repo = repo
        self.selected_owner = repo.get('owner', {}).get('login')
        self.selected_repo_name = repo.get('name')

        default_branch = repo.get('default_branch', '')
        if not self.branch_var.get().strip():
            self.branch_var.set(default_branch)
        self.load_repo_root()

    def load_repo_root(self):
        if not self.client or not self.selected_repo:
            return

        owner = self.selected_owner
        repo = self.selected_repo_name
        branch = self.branch_var.get().strip() or None

        self.log(f'Loading repo tree: {owner}/{repo}  branch={branch or "(default)"}')

        # Reset tree
        for i in self.tree.get_children(''):
            self.tree.delete(i)

        root_id = self.tree.insert('', 'end', text=f'{owner}/{repo}', values=('root',), open=True)
        self.tree.set(root_id, 'type', 'root')
        self.tree.item(root_id, tags=('folder',))
        self.tree.tag_configure('folder')
        self.tree.tag_configure('file')

        # Add a placeholder child so expand arrow shows
        ph = self.tree.insert(root_id, 'end', text='(loading...)', values=('placeholder',))
        self.tree.set(ph, 'type', 'placeholder')

        def work():
            try:
                items = self.client.get_contents(owner, repo, path='', ref=branch)
                self.after(0, lambda: self._populate_children(root_id, items))
            except Exception as e:
                self.after(0, lambda: self.log(f'Tree load failed: {e}'))
                self.after(0, lambda: messagebox.showerror('Tree load failed', str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _populate_children(self, parent_id, items):
        # Clear placeholders
        for cid in self.tree.get_children(parent_id):
            if self.tree.set(cid, 'type') == 'placeholder':
                self.tree.delete(cid)

        if not isinstance(items, list):
            return

        # GitHub returns dirs and files mixed; we sort to show folders first.
        dirs = [x for x in items if x.get('type') == 'dir']
        files = [x for x in items if x.get('type') == 'file']
        dirs.sort(key=lambda x: (x.get('name') or '').lower())
        files.sort(key=lambda x: (x.get('name') or '').lower())

        for it in dirs + files:
            name = it.get('name', '')
            typ = it.get('type', '')
            node_id = self.tree.insert(parent_id, 'end', text=name, values=(typ,))
            self.tree.set(node_id, 'type', typ)
            self.tree.item(node_id, tags=('folder',) if typ == 'dir' else ('file',))

            # store full path + sha
            self.tree.set(node_id, 'type', typ)
            self.tree.item(node_id, values=(typ,))
            self.tree.set(node_id, 'type', typ)
            self.tree.item(node_id, tags=('folder',) if typ == 'dir' else ('file',))
            self.tree.item(node_id, open=False)
            self.tree.set(node_id, 'type', typ)

            # attach metadata in a dict via "tags" is not great; we keep a side map
            if not hasattr(self, '_node_meta'):
                self._node_meta = {}
            self._node_meta[node_id] = {
                'path': it.get('path', ''),
                'sha': it.get('sha', ''),
                'type': typ,
            }

            if typ == 'dir':
                ph = self.tree.insert(node_id, 'end', text='(loading...)', values=('placeholder',))
                self.tree.set(ph, 'type', 'placeholder')

    def _on_tree_open(self, _evt):
        sel = self.tree.selection()
        if not sel:
            return
        node_id = sel[0]
        meta = getattr(self, '_node_meta', {}).get(node_id)
        if not meta or meta.get('type') != 'dir':
            return

        # If already loaded (no placeholder), do nothing
        has_placeholder = False
        for cid in self.tree.get_children(node_id):
            if self.tree.set(cid, 'type') == 'placeholder':
                has_placeholder = True
                break
        if not has_placeholder:
            return

        owner = self.selected_owner
        repo = self.selected_repo_name
        branch = self.branch_var.get().strip() or None
        path = meta.get('path', '')

        def work():
            try:
                items = self.client.get_contents(owner, repo, path=path, ref=branch)
                self.after(0, lambda: self._populate_children(node_id, items))
            except Exception as e:
                self.after(0, lambda: self.log(f'Folder load failed: {e}'))

        threading.Thread(target=work, daemon=True).start()

    def _on_tree_selected(self, _evt):
        sel = self.tree.selection()
        if not sel:
            return
        node_id = sel[0]
        meta = getattr(self, '_node_meta', {}).get(node_id)
        if not meta or meta.get('type') != 'file':
            self._set_preview('')
            return

        owner = self.selected_owner
        repo = self.selected_repo_name
        branch = self.branch_var.get().strip() or None
        path = meta.get('path', '')

        self.log(f'Loading file preview: {path}')

        def work():
            try:
                text, _obj = self.client.get_file_text(owner, repo, path, ref=branch)
                self.after(0, lambda: self._set_preview(text))
            except Exception as e:
                self.after(0, lambda: self._set_preview(f'[Preview not available]\n{e}'))

        threading.Thread(target=work, daemon=True).start()

    def _set_preview(self, text):
        self.preview_text.configure(state='normal')
        self.preview_text.delete('1.0', 'end')
        self.preview_text.insert('1.0', text)
        self.preview_text.configure(state='disabled')

    def _get_selected_file_node(self):
        sel = self.tree.selection()
        if not sel:
            return None, None
        node_id = sel[0]
        meta = getattr(self, '_node_meta', {}).get(node_id)
        if not meta:
            return None, None
        return node_id, meta

    def copy_selected_path(self):
        _nid, meta = self._get_selected_file_node()
        if not meta:
            return
        path = meta.get('path', '')
        if not path:
            return
        self.clipboard_clear()
        self.clipboard_append(path)
        self.log(f'Copied path: {path}')

    def delete_selected_dialog(self):
        node_id, meta = self._get_selected_file_node()
        if not meta:
            return
        if meta.get('type') != 'file':
            messagebox.showinfo('Delete', 'Select a file to delete.')
            return

        path = meta.get('path', '')
        sha = meta.get('sha', '')
        if not sha:
            messagebox.showerror('Delete failed', 'Missing SHA for selected file.')
            return

        msg = simpledialog.askstring('Commit message', f"Delete {path}\n\nCommit message:")
        if not msg:
            return

        if not messagebox.askyesno('Confirm delete', f"Delete file from repo?\n\n{path}"):
            return

        owner = self.selected_owner
        repo = self.selected_repo_name
        branch = self.branch_var.get().strip() or None

        self.log(f'Deleting: {path}')

        def work():
            try:
                self.client.delete_file(owner, repo, path, msg, sha, branch=branch)
                self.after(0, lambda: self.log('Delete complete.'))
                self.after(0, self.load_repo_root)
            except Exception as e:
                self.after(0, lambda: self.log(f'Delete failed: {e}'))
                self.after(0, lambda: messagebox.showerror('Delete failed', str(e)))

        threading.Thread(target=work, daemon=True).start()

    def upload_files_dialog(self):
        if not self.selected_repo:
            return

        file_paths = filedialog.askopenfilenames(title='Select file(s) to upload')
        if not file_paths:
            return

        target_folder = simpledialog.askstring('Target folder', 'Repo folder path (blank = root):')
        if target_folder is None:
            return
        target_folder = target_folder.strip().strip('/')

        msg = simpledialog.askstring('Commit message', 'Commit message:')
        if not msg:
            return

        owner = self.selected_owner
        repo = self.selected_repo_name
        branch = self.branch_var.get().strip() or None

        self.log(f'Uploading {len(file_paths)} file(s)...')

        def work():
            for fp in file_paths:
                try:
                    name = os.path.basename(fp)
                    repo_path = f'{target_folder}/{name}' if target_folder else name

                    # If file exists, fetch sha and overwrite.
                    sha = None
                    try:
                        existing = self.client.get_contents(owner, repo, repo_path, ref=branch)
                        if isinstance(existing, dict) and existing.get('type') == 'file':
                            sha = existing.get('sha')
                    except Exception:
                        sha = None

                    with open(fp, 'rb') as f:
                        content = f.read()

                    self.client.put_file(owner, repo, repo_path, content, msg, branch=branch, sha=sha)
                    self.after(0, lambda p=repo_path: self.log(f'Uploaded: {p}'))
                except Exception as e:
                    self.after(0, lambda p=fp, err=e: self.log(f'Upload failed: {p}  {err}'))

            self.after(0, lambda: self.log('Upload complete.'))
            self.after(0, self.load_repo_root)

        threading.Thread(target=work, daemon=True).start()

    def download_selected_dialog(self):
        node_id, meta = self._get_selected_file_node()
        if not meta or meta.get('type') != 'file':
            messagebox.showinfo('Download', 'Select a file to download.')
            return

        path = meta.get('path', '')
        if not path:
            return

        save_as = filedialog.asksaveasfilename(title='Save file as', initialfile=os.path.basename(path))
        if not save_as:
            return

        owner = self.selected_owner
        repo = self.selected_repo_name
        branch = self.branch_var.get().strip() or None

        self.log(f'Downloading: {path}')

        def work():
            try:
                text, obj = self.client.get_file_text(owner, repo, path, ref=branch)
                # If the API returned base64 text for binary, decode directly via obj content.
                raw = None
                if obj.get('encoding') == 'base64':
                    import base64
                    raw = base64.b64decode(obj.get('content', ''))
                else:
                    raw = text.encode('utf-8')

                with open(save_as, 'wb') as f:
                    f.write(raw)

                self.after(0, lambda: self.log(f'Saved to: {save_as}'))
            except Exception as e:
                self.after(0, lambda: self.log(f'Download failed: {e}'))
                self.after(0, lambda: messagebox.showerror('Download failed', str(e)))

        threading.Thread(target=work, daemon=True).start()

    def create_repo_dialog(self):
        if not self.client:
            return

        dlg = tk.Toplevel(self)
        dlg.title('Create Repo')
        dlg.geometry('520x240')
        dlg.transient(self)
        dlg.grab_set()

        name_var = tk.StringVar(value='')
        desc_var = tk.StringVar(value='')
        priv_var = tk.BooleanVar(value=True)
        init_var = tk.BooleanVar(value=True)

        frm = ttk.Frame(dlg)
        frm.pack(fill='both', expand=True, padx=10, pady=10)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text='Name:').grid(row=0, column=0, sticky='w', pady=4)
        ttk.Entry(frm, textvariable=name_var).grid(row=0, column=1, sticky='ew', pady=4)

        ttk.Label(frm, text='Description:').grid(row=1, column=0, sticky='w', pady=4)
        ttk.Entry(frm, textvariable=desc_var).grid(row=1, column=1, sticky='ew', pady=4)

        ttk.Checkbutton(frm, text='Private', variable=priv_var).grid(row=2, column=1, sticky='w', pady=4)
        ttk.Checkbutton(frm, text='Initialize with README', variable=init_var).grid(row=3, column=1, sticky='w', pady=4)

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=1, sticky='e', pady=10)

        def create_now():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning('Create repo', 'Name is required.')
                return
            desc = desc_var.get().strip()
            private = priv_var.get()
            auto_init = init_var.get()

            self.log(f'Creating repo: {name}')

            def work():
                try:
                    self.client.create_repo(name=name, private=private, description=desc, auto_init=auto_init)
                    self.after(0, lambda: self.log('Repo created.'))
                    self.after(0, self.refresh_repos)
                    self.after(0, dlg.destroy)
                except Exception as e:
                    self.after(0, lambda: self.log(f'Create repo failed: {e}'))
                    self.after(0, lambda: messagebox.showerror('Create repo failed', str(e)))

            threading.Thread(target=work, daemon=True).start()

        ttk.Button(btns, text='Create', command=create_now).pack(side='left')
        ttk.Button(btns, text='Cancel', command=dlg.destroy).pack(side='left', padx=(8, 0))

    
if __name__ == '__main__':
    app = GitHubEditorApp()
    app.mainloop()
