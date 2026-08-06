/*
 * Zotero 集合分类管理脚本 (v3 - 读取映射文件版)
 * 
 * 使用方法:
 * 1. 确保 d:\Desktop\论文\_venue_map.json 文件存在
 * 2. 打开 Zotero 桌面端
 * 3. 菜单栏: 工具 → 开发者 → Run JavaScript
 * 4. 确保勾选 "作为异步函数执行"
 * 5. 将本文件全部内容复制粘贴到代码框中
 * 6. 点击 "执行" (Ctrl+R)
 * 7. 等待 5-10 分钟
 * 
 * 功能:
 * - 读取 _venue_map.json 获取 title→venue 映射
 * - 创建 CCF-A 集合 (10 子领域) + MCM-ICM 集合 (7 题号)
 * - 给 CCF-A 条目添加正确的 venue 标签
 * - 按标签将条目分配到对应集合
 */

// ============ 配置 ============
var AREA_NAMES = {
    "AI": "AI (人工智能)",
    "Database": "Database (数据库/数据挖掘)",
    "Networks": "Networks (计算机网络)",
    "Security": "Security (网络与信息安全)",
    "Software": "Software (软件工程)",
    "Theory": "Theory (计算机科学理论)",
    "Graphics": "Graphics (计算机图形学)",
    "HCI": "HCI (人机交互)",
    "Architecture": "Architecture (体系结构)",
    "Interdisciplinary": "Interdisciplinary (交叉/综合/新兴)",
};

var VENUE_AREA = {
    "AAAI": "AI", "IJCAI": "AI", "ICML": "AI", "NeurIPS": "AI", "ICLR": "AI",
    "ACL": "AI", "EMNLP": "AI", "CVPR": "AI", "ICCV": "AI", "ECCV": "AI",
    "KR": "AI", "AAMAS": "AI", "COLT": "AI", "TPAMI": "AI", "IJCV": "AI",
    "JMLR": "AI", "AIJ": "AI",
    "SIGMOD": "Database", "VLDB": "Database", "ICDE": "Database", "KDD": "Database",
    "SIGIR": "Database", "WWW": "Database", "TKDE": "Database", "TOIS": "Database",
    "TODS": "Database", "VLDBJ": "Database",
    "SIGCOMM": "Networks", "NSDI": "Networks", "INFOCOM": "Networks", "CoNEXT": "Networks",
    "TON": "Networks", "JSAC": "Networks",
    "SP": "Security", "CCS": "Security", "USENIXSec": "Security", "NDSS": "Security",
    "CRYPTO": "Security", "EUROCRYPT": "Security", "TIFS": "Security", "TDSC": "Security",
    "JCS": "Security",
    "ICSE": "Software", "FSE": "Software", "ASE": "Software", "ISSTA": "Software",
    "POPL": "Software", "PLDI": "Software", "OOPSLA": "Software", "TOSEM": "Software",
    "TSE": "Software", "TOPS": "Software",
    "STOC": "Theory", "FOCS": "Theory", "SODA": "Theory", "LICS": "Theory",
    "JACM": "Theory", "TOCT": "Theory", "SICOMP": "Theory",
    "SIGGRAPH": "Graphics", "CHI": "Graphics", "TOG": "Graphics", "TVCG": "Graphics",
    "UIST": "HCI", "CSCW": "HCI", "IUI": "HCI", "IMWUT": "HCI",
    "ISCA": "Architecture", "MICRO": "Architecture", "HPCA": "Architecture",
    "ASPLOS": "Architecture", "SC": "Architecture", "PPoPP": "Architecture",
    "DAC": "Architecture", "USENIX": "Architecture", "FAST": "Architecture",
    "TOCS": "Architecture", "TACO": "Architecture", "TC": "Architecture",
    "ICDM": "Interdisciplinary", "CIKM": "Interdisciplinary", "WSDM": "Interdisciplinary",
    "RecSys": "Interdisciplinary", "ICRA": "Interdisciplinary", "IROS": "Interdisciplinary",
    "TPDS": "Interdisciplinary", "TIST": "Interdisciplinary",
};

var PROBLEM_NAMES = {
    "A": "Problem A - MCM 连续型",
    "B": "Problem B - MCM 离散型",
    "C": "Problem C - MCM 数据分析",
    "D": "Problem D - ICM 运筹/网络",
    "E": "Problem E - ICM 可持续发展",
    "F": "Problem F - ICM 政策",
    "Unknown": "未分类",
};

var LIB_ID = Zotero.Libraries.userLibraryID;

// ============ 辅助函数 ============

async function findOrCreateCollection(name, parentID) {
    var allCols = Zotero.Collections.getByLibrary(LIB_ID);
    if (allCols) {
        for (var i = 0; i < allCols.length; i++) {
            var c = allCols[i];
            if (c.name === name) {
                if (parentID && c.parentID === parentID) return c.id;
                if (!parentID && !c.parentID) return c.id;
            }
        }
    }
    var col = new Zotero.Collection();
    col.libraryID = LIB_ID;
    col.name = name;
    if (parentID) col.parentID = parentID;
    var id = await col.saveTx();
    return id;
}

// ============ 第1步: 读取映射文件 ============
var mapPath = "d:\\Desktop\\论文\\_venue_map.json";
var fileContents = Zotero.File.getContents(mapPath);
var venueMap = JSON.parse(fileContents);
var mapSize = Object.keys(venueMap).length;

// ============ 第2步: 创建集合 ============
var ccfRootID = await findOrCreateCollection("CCF-A", null);
var areaIDs = {};
for (var area in AREA_NAMES) {
    areaIDs[area] = await findOrCreateCollection(AREA_NAMES[area], ccfRootID);
}

var mcmRootID = await findOrCreateCollection("MCM-ICM", null);
var problemIDs = {};
for (var prob in PROBLEM_NAMES) {
    problemIDs[prob] = await findOrCreateCollection(PROBLEM_NAMES[prob], mcmRootID);
}

// ============ 第3步: 获取所有条目 ============
var s = new Zotero.Search();
s.libraryID = LIB_ID;
s.addCondition('itemType', 'isNot', 'note');
s.addCondition('itemType', 'isNot', 'attachment');
var itemIDs = await s.search();

// ============ 第4步: 分配条目到集合 ============
var assigned = 0;
var noMatch = 0;
var alreadyIn = 0;
var tagAdded = 0;
var areaCounts = {};
var problemCounts = {};
for (var a in AREA_NAMES) areaCounts[a] = 0;
for (var p in PROBLEM_NAMES) problemCounts[p] = 0;

for (var i = 0; i < itemIDs.length; i++) {
    var item = await Zotero.Items.getAsync(itemIDs[i]);
    if (!item) continue;
    
    var tags = item.getTags().map(function(t) { return t.tag; });
    var title = item.getField('title') || '';
    var titleLower = title.toLowerCase().replace(/\.$/, '');
    
    var targetCollectionID = null;
    var venue = null;
    
    // 判断是否为 MCM/ICM 论文
    if (tags.indexOf('MCM-ICM') !== -1) {
        var found = false;
        var probs = ['A', 'B', 'C', 'D', 'E', 'F'];
        for (var j = 0; j < probs.length; j++) {
            if (tags.indexOf('Problem ' + probs[j]) !== -1) {
                targetCollectionID = problemIDs[probs[j]];
                problemCounts[probs[j]]++;
                found = true;
                break;
            }
        }
        if (!found) {
            var m = title.match(/Problem\s*([A-F])/i);
            if (m) {
                targetCollectionID = problemIDs[m[1].toUpperCase()];
                problemCounts[m[1].toUpperCase()]++;
            } else {
                targetCollectionID = problemIDs['Unknown'];
                problemCounts['Unknown']++;
            }
        }
    }
    // 判断是否为 CCF-A 论文
    else if (tags.indexOf('CCF-A') !== -1) {
        // 通过 title 查找 venue
        if (venueMap[titleLower]) {
            venue = venueMap[titleLower].venue;
        }
        
        // 如果找到 venue, 添加标签 (如果还没有)
        if (venue) {
            if (tags.indexOf(venue) === -1) {
                item.addTag(venue);
                tagAdded++;
            }
            var area = VENUE_AREA[venue];
            if (area) {
                targetCollectionID = areaIDs[area];
                areaCounts[area]++;
            }
        }
        
        // 如果没找到 venue, 尝试从已有标签中匹配
        if (!targetCollectionID) {
            for (var j = 0; j < tags.length; j++) {
                if (VENUE_AREA[tags[j]]) {
                    targetCollectionID = areaIDs[VENUE_AREA[tags[j]]];
                    areaCounts[VENUE_AREA[tags[j]]]++;
                    break;
                }
            }
        }
    }
    
    if (targetCollectionID) {
        var currentCollections = item.getCollections();
        if (currentCollections.indexOf(targetCollectionID) !== -1) {
            alreadyIn++;
        } else {
            item.addToCollection(targetCollectionID);
            await item.saveTx();
            assigned++;
        }
    } else {
        noMatch++;
    }
    
    if ((i + 1) % 1000 === 0) {
        Zotero.debug("进度: " + (i + 1) + "/" + itemIDs.length + " (已分配: " + assigned + ", 已添加标签: " + tagAdded + ")");
    }
}

// ============ 汇总 ============
var result = "===== 集合分类完成 =====\n";
result += "映射文件条目: " + mapSize + "\n";
result += "总条目: " + itemIDs.length + "\n";
result += "已分配: " + assigned + "\n";
result += "已在集合中: " + alreadyIn + "\n";
result += "无法分类: " + noMatch + "\n";
result += "新增 venue 标签: " + tagAdded + "\n";
result += "\nCCF-A 子领域分配:\n";
for (var area in AREA_NAMES) {
    result += "  " + AREA_NAMES[area] + ": " + areaCounts[area] + " 篇\n";
}
result += "\nMCM-ICM 题号分配:\n";
for (var prob in PROBLEM_NAMES) {
    result += "  " + PROBLEM_NAMES[prob] + ": " + problemCounts[prob] + " 篇\n";
}

result;
