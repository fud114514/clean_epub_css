import os
import re
import zipfile
import shutil
# import argparse # 不再需要命令行参数处理
import tempfile
import uuid # 用于生成唯一的临时文件名
import sys # 用于获取脚本路径

# 用于移除 CSS 元素的正则表达式
# ((text-indent|line-height|font-size|height|font-family|color)\s*:\s*[^;]*;|display\s*:\s*block\s*;)
CSS_REMOVE_PATTERN = re.compile(
    r'((text-indent|line-height|font-size|height|font-family|color)\s*:\s*[^;]*;|display\s*:\s*block\s*;)',
    re.IGNORECASE
)

def clean_css_content(css_content):
    """使用正则表达式移除 CSS 内容中的指定样式"""
    return CSS_REMOVE_PATTERN.sub('', css_content)

def process_epub_inplace(epub_path):
    """直接处理单个 EPUB 文件"""
    base_name = os.path.basename(epub_path)
    temp_output_epub_path = None # 初始化临时输出路径
    temp_dir = None # 初始化临时解压目录

    try:
        print(f"开始处理 (原地修改): {base_name}")

        # 1. 创建临时解压目录
        temp_dir = tempfile.mkdtemp()

        # 2. 解压 EPUB 到临时目录
        try:
            with zipfile.ZipFile(epub_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
        except zipfile.BadZipFile:
            print(f"  错误: {base_name} 不是一个有效的 EPUB (ZIP) 文件，已跳过。")
            return False # 返回失败
        except Exception as e:
            print(f"  错误: 解压 {base_name} 时出错: {e}")
            return False # 返回失败

        # 3. 遍历临时目录，修改 CSS 文件
        css_files_found = False
        modified = False
        for root, _, files in os.walk(temp_dir):
            for file in files:
                if file.lower().endswith('.css'):
                    css_files_found = True
                    css_file_path = os.path.join(root, file)
                    original_content = ""
                    try:
                        # 尝试 UTF-8 编码读取
                        with open(css_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            original_content = f.read()
                    except Exception as e:
                         print(f"  警告: 读取 CSS 文件 {file} 时出错 (错误: {e})，跳过。")
                         continue # 继续处理下一个文件

                    cleaned_content = clean_css_content(original_content)

                    # 如果内容有变化，则写回文件
                    if cleaned_content != original_content:
                        try:
                            with open(css_file_path, 'w', encoding='utf-8') as f:
                                f.write(cleaned_content)
                            print(f"  已清理: {os.path.join(os.path.relpath(root, temp_dir), file)}") # 显示相对路径
                            modified = True
                        except Exception as e:
                            print(f"  警告: 写入清理后的 CSS 文件 {file} 时出错 (错误: {e})。")
                            # 决定是否要回滚或继续，这里选择继续，但标记为未成功

        if not css_files_found:
             print(f"  信息: 在 {base_name} 中未找到 CSS 文件。")
             return True # 返回成功，但未修改

        if not modified:
            print(f"  信息: CSS 文件无需修改。")
            return True # 返回成功，但未修改


        # 4. 创建一个临时的 ZIP 文件名用于重新打包
        temp_output_epub_path = epub_path + f".{uuid.uuid4()}.tmpzip"

        # 5. 重新打包修改后的内容到临时 ZIP 文件
        print(f"  正在重新打包修改后的内容...")
        try:
             with zipfile.ZipFile(temp_output_epub_path, 'w', zipfile.ZIP_DEFLATED) as new_zip:
                # 确保 mimetype 文件是第一个且未压缩
                mimetype_path = os.path.join(temp_dir, 'mimetype')
                if os.path.exists(mimetype_path):
                     new_zip.write(mimetype_path, 'mimetype', compress_type=zipfile.ZIP_STORED)

                # 添加其他文件和目录
                for root, dirs, files in os.walk(temp_dir):
                     # 排除 mimetype 文件（如果它在根目录）
                     if root == temp_dir and 'mimetype' in files:
                         files.remove('mimetype')

                     for file in files:
                         file_path = os.path.join(root, file)
                         arcname = os.path.relpath(file_path, temp_dir)
                         new_zip.write(file_path, arcname)
        except Exception as e:
             print(f"  错误: 重新打包 {base_name} 时出错: {e}")
             # 如果打包失败，尝试删除临时zip文件
             if temp_output_epub_path and os.path.exists(temp_output_epub_path):
                 os.remove(temp_output_epub_path)
             return False # 返回失败

        # 6. 替换原文件 (关键步骤!)
        print(f"  正在替换原文件...")
        try:
            shutil.move(temp_output_epub_path, epub_path)
            temp_output_epub_path = None # 标记为已移动，避免在 finally 中被删除
            print(f"处理完成 (原地修改): {base_name}")
            return True # 返回成功

        except Exception as e:
            print(f"  错误: 替换原文件 {base_name} 时出错: {e}")
            # 替换失败，原文件应该还在，尝试删除临时zip
            if temp_output_epub_path and os.path.exists(temp_output_epub_path):
                os.remove(temp_output_epub_path)
            return False # 返回失败

    except Exception as e:
        # 捕获未预料的错误
        print(f"处理 {base_name} 时发生意外错误: {e}")
        if temp_output_epub_path and os.path.exists(temp_output_epub_path):
             try: os.remove(temp_output_epub_path)
             except OSError: pass
        return False # 返回失败
    finally:
        # 确保临时解压目录总是被清理
        if temp_dir and os.path.exists(temp_dir):
            try: shutil.rmtree(temp_dir)
            except OSError as e: print(f"  警告: 清理临时目录 {temp_dir} 时出错: {e}")
        # 确保未被移动的临时zip文件被清理
        if temp_output_epub_path and os.path.exists(temp_output_epub_path):
             try: os.remove(temp_output_epub_path)
             except OSError: pass


def get_script_directory():
    """获取脚本文件所在的目录"""
    # sys.executable 是 Python 解释器的路径
    # sys.argv[0] 是被执行的脚本的路径
    # __file__ 是当前模块的文件路径（在直接运行时通常是脚本路径）
    # 使用 __file__ 更为可靠
    try:
        # 如果脚本被打包成可执行文件（如 PyInstaller），__file__ 可能不存在
        if getattr(sys, 'frozen', False):
             # PyInstaller 创建一个临时文件夹并将脚本解压到其中
             return os.path.dirname(sys.executable)
        else:
             return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        # 在某些交互式环境或特殊执行方式下 __file__ 可能未定义
        # 作为备选，尝试使用 argv[0]
        try:
            return os.path.dirname(os.path.abspath(sys.argv[0]))
        except:
            # 如果一切都失败了，返回当前工作目录，但这可能不是用户期望的
            print("警告：无法准确确定脚本所在目录，将使用当前工作目录。")
            return os.getcwd()


def main():
    # 获取脚本所在的目录
    script_dir = get_script_directory()
    input_directory = script_dir # 明确指定处理脚本所在目录

    print(f"将在脚本所在目录 '{input_directory}' 中查找并原地修改 EPUB 文件...")
    print(f"将移除以下 CSS 样式: text-indent, line-height, font-size, height, font-family, color, display:block")
    print("警告: 操作将直接修改原文件！建议提前备份。")
    print("-" * 20) # 分隔线

    processed_count = 0
    error_count = 0
    found_epub = False

    try:
        all_items = os.listdir(input_directory)
    except OSError as e:
        print(f"错误: 无法访问目录 '{input_directory}': {e}")
        # 在脚本退出前给用户看错误信息
        input("按 Enter 键退出...")
        return

    # 获取脚本自身的文件名，避免处理脚本文件（如果它恰好是.epub）
    script_filename = os.path.basename(sys.argv[0])

    for itemname in all_items:
        # 忽略脚本文件自身
        if itemname == script_filename:
             continue

        item_path = os.path.join(input_directory, itemname)
        # 只处理目录中的文件，不处理子目录，且是 epub 文件
        if os.path.isfile(item_path) and itemname.lower().endswith('.epub'):
            found_epub = True
            result = process_epub_inplace(item_path)
            if result:
                processed_count += 1
            else:
                error_count += 1

    print("-" * 20) # 分隔线
    if not found_epub:
         print("在脚本所在目录中未找到 EPUB 文件。")
    else:
        print("\n--- 任务完成 ---")
        print(f"已尝试处理文件数: {processed_count + error_count}")
        print(f"处理成功（包含未修改）文件数: {processed_count}")
        print(f"处理失败文件数: {error_count}")
        if error_count > 0:
             print("请检查上面的错误或警告信息。失败的文件应保持原样。")

    # 在脚本结束前暂停，以便用户可以看到输出（特别是在双击运行时）
    input("\n按 Enter 键退出...")


if __name__ == "__main__":
    main()