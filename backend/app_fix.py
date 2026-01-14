# 临时修复文件 - 修复第1462行的缩进
# 读取原文件
with open('backend/app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 修复第1462行（索引是1461，因为从0开始）
if len(lines) > 1461:
    # 检查当前行
    if lines[1461].strip().startswith('return jsonify'):
        # 替换为正确缩进的版本
        lines[1461] = '        return jsonify({\n'
        # 修复后续行的缩进
        for i in range(1462, min(1467, len(lines))):
            if lines[i].strip().startswith("'platform'") or lines[i].strip().startswith("'email'") or lines[i].strip().startswith("'remaining'") or lines[i].strip().startswith("'message'"):
                lines[i] = '            ' + lines[i].lstrip()
            elif lines[i].strip() == '})':
                lines[i] = '        })\n'

# 写回文件
with open('backend/app.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("修复完成")
