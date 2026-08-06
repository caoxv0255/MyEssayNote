/*
 * Zotero 重复集合清理脚本 (v5 - 第二轮)
 * 删除剩余 16 个重复集合
 * 注意: 删除集合不会删除条目, 条目会保留在另一个同名的集合中
 * 
 * 使用方法:
 * 1. 打开 Zotero > 工具 > 开发者 > Run JavaScript
 * 2. 确保勾选 "作为异步函数执行"
 * 3. 粘贴本代码, 点击 "执行"
 */

var LIB_ID = Zotero.Libraries.userLibraryID;

var keysToDelete = [
    "MBQ66KWA", "TXC3ZGVA", "DAFBDCYL", "BHKWDKQ4", "HL2ECTWB", "RNS848YL",
    "NH5396FX", "2UCF8TJ8", "2Z4WKFJ8", "WRJ3QAYB", "GMZ8B3MT", "7YJ7AZWH",
    "ETITJCW8", "HEINHPYQ", "ACM5FX4E", "5BM7E3M2"
];

var deleted = 0;
var failed = 0;

for (var i = 0; i < keysToDelete.length; i++) {
    var col = Zotero.Collections.getByLibraryAndKey(LIB_ID, keysToDelete[i]);
    if (col) {
        await col.eraseTx();
        deleted++;
    } else {
        failed++;
    }
}

// 列出最终集合
var finalCols = Zotero.Collections.getByLibrary(LIB_ID);
var result = "===== 集合清理完成 =====\n";
result += "删除集合: " + deleted + "\n";
result += "未找到: " + failed + "\n";
result += "最终集合数: " + finalCols.length + "\n\n";
result += "最终集合列表:\n";

for (var i = 0; i < finalCols.length; i++) {
    var c = finalCols[i];
    var parentName = "";
    if (c.parentID) {
        var parent = Zotero.Collections.get(c.parentID);
        if (parent) parentName = parent.name;
    }
    result += "  " + c.name + (parentName ? " [父: " + parentName + "]" : " [根]") + "\n";
}

result;
