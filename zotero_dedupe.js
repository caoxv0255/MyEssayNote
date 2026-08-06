/*
 * Zotero 自动去重脚本
 * 
 * 功能: 查找标题相同的重复条目, 保留一个 (标签/集合最完整的), 删除其余
 * 
 * 使用方法:
 * 1. 打开 Zotero > 工具 > 开发者 > Run JavaScript
 * 2. 确保勾选 "作为异步函数执行"
 * 3. 粘贴本代码, 点击 "执行"
 * 4. 等待 5-10 分钟 (14629 条目需要逐一处理)
 * 
 * 注意: 脚本会先将要删除的条目移入回收站, 不会永久删除
 *       如需恢复, 可在 Zotero 回收站中找到
 */

var LIB_ID = Zotero.Libraries.userLibraryID;

// 第1步: 获取所有条目 (不含回收站)
var s = new Zotero.Search();
s.libraryID = LIB_ID;
s.addCondition('itemType', 'isNot', 'note');
s.addCondition('itemType', 'isNot', 'attachment');
s.addCondition('deleted', 'false');  // 排除已删除的条目
var itemIDs = await s.search();

// 第2步: 按标题分组
var byTitle = {};
var items = [];

for (var i = 0; i < itemIDs.length; i++) {
    var item = await Zotero.Items.getAsync(itemIDs[i]);
    if (!item) continue;
    
    var title = item.getField('title') || '';
    var titleLower = title.toLowerCase().trim();
    
    if (!byTitle[titleLower]) {
        byTitle[titleLower] = [];
    }
    
    // 记录条目信息和"完整度"分数 (标签数+集合数)
    var tags = item.getTags();
    var collections = item.getCollections();
    var score = tags.length + collections.length * 2; // 集合权重更高
    
    byTitle[titleLower].push({
        item: item,
        id: item.id,
        score: score,
        tags: tags.length,
        collections: collections.length,
    });
}

// 第3步: 找出重复条目
var toDelete = [];
var dupGroups = 0;

for (var title in byTitle) {
    var group = byTitle[title];
    if (group.length <= 1) continue;
    
    dupGroups++;
    
    // 按 score 降序排列, 保留 score 最高的
    group.sort(function(a, b) { return b.score - a.score; });
    
    // 保留第一个, 其余标记为删除
    for (var j = 1; j < group.length; j++) {
        toDelete.push(group[j].id);
    }
}

// 第4步: 删除重复条目 (移入回收站)
var deleted = 0;
for (var i = 0; i < toDelete.length; i++) {
    var item = await Zotero.Items.getAsync(toDelete[i]);
    if (item) {
        // 移入回收站 (不永久删除)
        item.deleted = true;
        await item.saveTx();
        deleted++;
    }
    
    if ((i + 1) % 200 === 0) {
        Zotero.debug("去重进度: " + (i + 1) + "/" + toDelete.length);
    }
}

// 第5步: 汇总
var result = "===== 自动去重完成 =====\n";
result += "总条目: " + itemIDs.length + "\n";
result += "重复标题组: " + dupGroups + "\n";
result += "删除重复条目: " + deleted + "\n";
result += "保留条目: " + (itemIDs.length - deleted) + "\n";
result += "\n注意: 已删除的条目移入了回收站。\n";
result += "如需恢复: Zotero > 回收站 > 右键 > 恢复到原位置\n";
result += "如需永久删除: 清空回收站即可\n";

result;
