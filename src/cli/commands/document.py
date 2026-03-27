"""文档管理命令"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from src.cli.api_client import api_client
from src.cli.utils import format_size, confirm_action

app = typer.Typer(name="doc", help="文档管理")
console = Console()


@app.command("list")
def list_documents(
    project_id: str = typer.Argument(..., help="项目ID"),
    limit: int = typer.Option(100, "--limit", "-l", help="返回数量"),
):
    """列出项目文档"""
    result = api_client.get(
        f"/api/v1/projects/{project_id}/documents",
        params={"limit": limit},
    )
    
    if not result or not result.get("success"):
        console.print("[red]获取文档列表失败[/red]")
        return
    
    data = result.get("data", [])
    if isinstance(data, dict):
        data = data.get("items", data.get("documents", []))
    
    if not data:
        console.print("[yellow]项目中没有文档[/yellow]")
        return
    
    table = Table(title=f"📄 文档列表 (共 {len(data)} 个)")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("文件名", style="magenta")
    table.add_column("大小", justify="right")
    table.add_column("类型", style="green")
    table.add_column("状态", justify="center")
    
    for doc in data:
        doc_id = doc.get("id", "")
        file_size = doc.get("file_size", 0)
        file_type = Path(doc.get("name", "unknown")).suffix or "unknown"
        index_status = "✓ 已索引" if doc.get("indexed") else "○ 待索引"
        
        table.add_row(
            doc_id[:12] + "..." if len(doc_id) > 12 else doc_id,
            doc.get("name", "-"),
            format_size(file_size) if file_size else "-",
            file_type,
            index_status,
        )
    
    console.print(table)


@app.command()
def upload(
    project_id: str = typer.Argument(..., help="项目ID"),
    file_path: Path = typer.Argument(..., help="文件路径"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="递归处理目录"),
):
    """上传文档"""
    if not file_path.exists():
        console.print(f"[red]文件不存在: {file_path}[/red]")
        raise typer.Exit(1)
    
    files_to_upload = []
    
    if file_path.is_file():
        files_to_upload = [file_path]
    elif file_path.is_dir():
        pattern = "**/*" if recursive else "*"
        files_to_upload = [f for f in file_path.glob(pattern) if f.is_file()]
    
    if not files_to_upload:
        console.print("[yellow]没有找到要上传的文件[/yellow]")
        return
    
    console.print(f"[bold]准备上传 {len(files_to_upload)} 个文件...[/bold]\n")
    
    success_count = 0
    fail_count = 0
    
    for f in files_to_upload:
        console.print(f"  上传: {f.name}...", end=" ", style="cyan")
        
        result = api_client.upload_file(
            f"/api/v1/projects/{project_id}/documents",
            f,
        )
        
        if result and result.get("success"):
            console.print("[green]✓[/green]")
            success_count += 1
        else:
            console.print("[red]✗[/red]")
            fail_count += 1
    
    console.print(f"\n[bold]完成: {success_count} 成功, {fail_count} 失败[/bold]")


@app.command()
def delete(
    project_id: str = typer.Argument(..., help="项目ID"),
    doc_id: str = typer.Argument(..., help="文档ID"),
    force: bool = typer.Option(False, "--force", "-f", help="强制删除"),
):
    """删除文档"""
    if not force:
        if not confirm_action(f"确定要删除文档 {doc_id} 吗？"):
            console.print("[yellow]已取消[/yellow]")
            return
    
    result = api_client.delete(f"/api/v1/projects/{project_id}/documents/{doc_id}")
    
    if result and result.get("success"):
        console.print(f"[green]✓ 文档已删除[/green]")
    else:
        console.print(f"[red]✗ 删除失败: {result.get('message', '未知错误')}[/red]")


@app.command()
def export(
    project_id: str = typer.Argument(..., help="项目ID"),
    doc_id: str = typer.Argument(..., help="文档ID"),
    output: Path = typer.Option(None, "--output", "-o", help="输出文件路径"),
    format: str = typer.Option("txt", "--format", "-f", help="输出格式 (txt/markdown/json)"),
):
    """导出文档内容"""
    result = api_client.get(
        f"/api/v1/projects/{project_id}/documents/{doc_id}/export",
        params={"format": format},
    )
    
    if not result or not result.get("success"):
        console.print(f"[red]导出失败[/red]")
        return
    
    data = result.get("data", {})
    content = data.get("content", "") if isinstance(data, dict) else str(data)
    
    if output:
        output.write_text(content)
        console.print(f"[green]✓ 已保存到: {output}[/green]")
    else:
        console.print(content)
