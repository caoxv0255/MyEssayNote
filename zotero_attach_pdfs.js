/*
 * Zotero PDF 附件关联脚本
 * 
 * 功能:
 * 1. 将 MCM/ICM 本地 PDF 文件关联到 Zotero 条目
 * 2. 用 DOI/arXiv ID 查找并下载 CCF-A 论文 PDF
 * 
 * 使用方法:
 * 1. 打开 Zotero > 工具 > 开发者 > Run JavaScript
 * 2. 确保勾选 "作为异步函数执行"
 * 3. 粘贴本代码, 点击 "执行"
 * 4. 等待完成 (MCM 约5分钟, CCF-A 视网络而定)
 */

var LIB_ID = Zotero.Libraries.userLibraryID;
var MCM_DIR = "d:\\Desktop\\论文\\MCM-ICM";

// ============ 第1步: 关联 MCM/ICM 本地 PDF ============

// 获取所有 MCM-ICM 条目
var s = new Zotero.Search();
s.libraryID = LIB_ID;
s.addCondition('itemType', 'isNot', 'note');
s.addCondition('itemType', 'isNot', 'attachment');
s.addCondition('deleted', 'false');
s.addCondition('tag', 'is', 'MCM-ICM');
var mcmItemIDs = await s.search();

var mcmAttached = 0;
var mcmSkipped = 0;
var mcmNotFound = 0;

for (var i = 0; i < mcmItemIDs.length; i++) {
    var item = await Zotero.Items.getAsync(mcmItemIDs[i]);
    if (!item) continue;
    
    var title = item.getField('title') || '';
    
    // 检查是否已有附件
    var existingAttachments = item.getAttachments();
    if (existingAttachments && existingAttachments.length > 0) {
        mcmSkipped++;
        continue;
    }
    
    // 从标题提取年份和题号
    // 标题格式: "MCM/ICM 2023 Problem A - B-18-Successful"
    var yearMatch = title.match(/(20\d{2})/);
    var probMatch = title.match(/Problem\s*([A-F])/i);
    
    if (!yearMatch) {
        mcmNotFound++;
        continue;
    }
    
    var year = yearMatch[1];
    var problem = probMatch ? probMatch[1].toUpperCase() : 'Unknown';
    var probFolder = problem === 'Unknown' ? 'Unknown' : 'Problem_' + problem;
    
    // 从标题提取文件名部分 (最后一个 - 后面的部分)
    var parts = title.split(' - ');
    var fileName = parts.length > 1 ? parts[parts.length - 1].trim() : '';
    
    if (!fileName) {
        mcmNotFound++;
        continue;
    }
    
    // 尝试多种文件扩展名
    var extensions = ['.pdf', '.doc', '.docx'];
    var filePath = null;
    
    for (var e = 0; e < extensions.length; e++) {
        var tryPath = MCM_DIR + "\\" + year + "\\" + probFolder + "\\" + fileName + extensions[e];
        if (Zotero.File.pathToFile(tryPath)) {
            filePath = tryPath;
            break;
        }
    }
    
    if (!filePath) {
        mcmNotFound++;
        continue;
    }
    
    // 创建附件
    var attachment = await Zotero.Attachments.importFromFile({
        file: filePath,
        parentItemID: item.id,
        libraryID: LIB_ID,
    });
    
    mcmAttached++;
    
    if ((i + 1) % 50 === 0) {
        Zotero.debug("MCM 附件进度: " + (i + 1) + "/" + mcmItemIDs.length + " (已关联: " + mcmAttached + ")");
    }
}

// ============ 第2步: CCF-A 论文 - 用 DOI 查找 arXiv PDF ============
// (仅处理有 DOI 且 DOI 包含 arxiv 的条目)

var s2 = new Zotero.Search();
s2.libraryID = LIB_ID;
s2.addCondition('itemType', 'isNot', 'note');
s2.addCondition('itemType', 'isNot', 'attachment');
s2.addCondition('deleted', 'false');
s2.addCondition('tag', 'is', 'CCF-A');
var ccfItemIDs = await s2.search();

var ccfArxiv = 0;
var ccfNoDOI = 0;
var ccfDownloaded = 0;
var ccfFailed = 0;

for (var i = 0; i < ccfItemIDs.length; i++) {
    var item = await Zotero.Items.getAsync(ccfItemIDs[i]);
    if (!item) continue;
    
    var doi = item.getField('DOI') || '';
    var url = item.getField('url') || '';
    
    // 检查是否已有附件
    var existingAttachments = item.getAttachments();
    if (existingAttachments && existingAttachments.length > 0) {
        continue;
    }
    
    // 尝试从 DOI 或 URL 中提取 arXiv ID
    var arxivId = null;
    
    // DOI 格式: 10.48550/arxiv.2301.00001
    var doiMatch = doi.match(/arxiv\.(\d{4}\.\d{4,5})/i);
    if (doiMatch) {
        arxivId = doiMatch[1];
    }
    
    // URL 格式: https://arxiv.org/abs/2301.00001
    if (!arxivId) {
        var urlMatch = url.match(/arxiv\.org\/(?:abs|pdf)\/(\d{4}\.\d{4,5})/i);
        if (urlMatch) {
            arxivId = urlMatch[1];
        }
    }
    
    if (!arxivId) {
        ccfNoDOI++;
        continue;
    }
    
    ccfArxiv++;
    
    // 下载 PDF
    var pdfUrl = "https://arxiv.org/pdf/" + arxivId + ".pdf";
    try {
        // 使用 Zotero 的 HTTP 请求
        var response = await Zotero.HTTP.request('GET', pdfUrl, {
            responseType: 'arraybuffer',
            timeout: 30000,
        });
        
        if (response.status === 200) {
            // 保存为临时文件
            var tempPath = Zotero.getTempDirectory().path + "\\arxiv_" + arxivId.replace('.', '_') + ".pdf";
            Zotero.File.putContents(tempPath, response.response);
            
            // 创建附件
            var attachment = await Zotero.Attachments.importFromFile({
                file: tempPath,
                parentItemID: item.id,
                libraryID: LIB_ID,
            });
            
            // 删除临时文件
            Zotero.File.removeIfExists(tempPath);
            
            ccfDownloaded++;
        } else {
            ccfFailed++;
        }
    } catch (e) {
        ccfFailed++;
    }
    
    // 限速 (arXiv 每3秒一次)
    await Zotero.Promise.delay(3000);
    
    if ((i + 1) % 100 === 0) {
        Zotero.debug("CCF-A PDF 下载进度: " + (i + 1) + "/" + ccfItemIDs.length + " (有arXiv: " + ccfArxiv + ", 已下载: " + ccfDownloaded + ")");
    }
    
    // 安全阀: 最多下载500个 (避免运行太久)
    if (ccfDownloaded >= 500) {
        Zotero.debug("达到500个下载上限, 停止");
        break;
    }
}

// ============ 汇总 ============
var result = "===== PDF 附件关联完成 =====\n\n";
result += "--- MCM/ICM 本地文件关联 ---\n";
result += "总条目: " + mcmItemIDs.length + "\n";
result += "已关联附件: " + mcmAttached + "\n";
result += "已有附件(跳过): " + mcmSkipped + "\n";
result += "未找到文件: " + mcmNotFound + "\n\n";
result += "--- CCF-A arXiv PDF 下载 ---\n";
result += "总条目: " + ccfItemIDs.length + "\n";
result += "有 arXiv ID: " + ccfArxiv + "\n";
result += "无 arXiv ID: " + ccfNoDOI + "\n";
result += "已下载: " + ccfDownloaded + "\n";
result += "下载失败: " + ccfFailed + "\n\n";
result += "提示: 大部分 CCF-A 论文没有 arXiv ID, 需要手动下载或使用 Zotero 的'查找可用PDF'功能。\n";
result += "操作: 选中条目 > 右键 > 查找可用 PDF\n";

result;
