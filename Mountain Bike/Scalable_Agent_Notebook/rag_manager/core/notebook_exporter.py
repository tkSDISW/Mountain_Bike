import nbformat as nbf

class NotebookExporter:
    def __init__(self, agent):
        self.agent = agent

    def export(self, filename="agent_replay.ipynb", minimal=True):
        history = self.agent.get_history()
        nb = nbf.v4.new_notebook()
        cells = []
    
        cells.append(nbf.v4.new_markdown_cell("# Agent Replay Notebook\nGenerated from agent history."))
    
        for i, record in enumerate(history):
            md = f"### Step {i+1}: Run `{record['tool']}`"
            if record.get("input"):
                if minimal and record["tool"] == "llm_chat":
                    md += f"\nPrompt: `{record['input'].get('prompt', '')}`"
                else:
                    md += f"\nInput: `{record['input']}`"
            cells.append(nbf.v4.new_markdown_cell(md))
    
            # Code cell: minimal replay for llm_chat
            if minimal and record["tool"] == "llm_chat":
                code = f"agent.run('llm_chat', input_data={{'prompt': '{record['input'].get('prompt', '')}'}})"
            else:
                code = f"agent.run('{record['tool']}', input_data={record.get('input') or {}})"
            cells.append(nbf.v4.new_code_cell(code))
    
        nb["cells"] = cells
        with open(filename, "w") as f:
            nbf.write(nb, f)
    
        return {"message": f"📓 Notebook exported to {filename}", "filename": filename}