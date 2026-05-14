# 更新日志 - 告警设置功能

## 版本: v4.2 (2026-05-14)

### ✨ 新增功能

#### 1. 告警设置管理
- **功能描述**: 允许管理员自定义需要监控的硬件类型
- **支持硬件**: CPU、GPU、内存、硬盘、网卡、主板、BIOS
- **配置方式**: 
  - Web界面：系统配置 -> 告警设置标签页
  - API接口：`GET/PUT /api/alert-settings`

#### 2. 灵活的监控规则
- 可以单独启用/禁用每种硬件类型的监控
- 默认配置：CPU、GPU、内存、硬盘启用，其他禁用
- 一键恢复默认设置功能

#### 3. 智能变更检测
- 根据告警设置动态调整检测逻辑
- 只对被监控的硬件类型进行变更对比
- 减少不必要的告警噪音

### 🔧 技术改进

#### 数据库变更
- 新增 `alert_settings` 表
  ```sql
  CREATE TABLE alert_settings (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      monitor_cpu INTEGER DEFAULT 1,
      monitor_gpu INTEGER DEFAULT 1,
      monitor_memory INTEGER DEFAULT 1,
      monitor_disk INTEGER DEFAULT 1,
      monitor_network INTEGER DEFAULT 0,
      monitor_motherboard INTEGER DEFAULT 0,
      monitor_bios INTEGER DEFAULT 0,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  )
  ```

#### API接口
- **GET /api/alert-settings** - 获取当前告警设置
- **PUT /api/alert-settings** - 更新告警设置

#### 后端优化
- 修改 `compare_hardware()` 函数
  - 新增 `alert_settings` 参数
  - 根据设置动态决定对比哪些硬件
  - 支持7种硬件类型的条件对比
  
- 修改 `receive_report()` 函数
  - 在硬件对比前读取告警设置
  - 传递设置到对比函数
  - 扩展基准快照包含更多硬件信息

#### 前端改进
- 重命名"邮件配置"为"系统配置"
- 添加Tab切换功能
  - Tab 1: 邮件配置（原有功能）
  - Tab 2: 告警设置（新增功能）
  
- 告警设置界面
  - 7个硬件类型的卡片式选择器
  - 实时显示监控说明
  - 保存和恢复默认按钮
  
- JavaScript功能
  - `loadAlertSettings()` - 加载设置
  - `switchConfigTab()` - Tab切换
  - 表单提交处理
  - 恢复默认功能

### 📁 文件变更清单

#### 修改的文件
1. `server/app.py`
   - 新增数据库表初始化代码
   - 修改 `compare_hardware()` 函数
   - 修改 `receive_report()` 函数
   - 新增 `get_alert_settings()` API
   - 新增 `update_alert_settings()` API

2. `server/templates/index.html`
   - 重构邮件配置模态框
   - 添加Tab切换结构
   - 新增告警设置UI
   - 新增JavaScript函数

#### 新增的文件
1. `server/test_alert_settings.py` - API测试脚本
2. `server/告警设置功能说明.md` - 详细功能文档
3. `server/告警设置快速开始.md` - 快速上手指南
4. `server/CHANGELOG_告警设置.md` - 本更新日志

### 🎯 使用场景

#### 场景1: 减少告警噪音
**问题**: 某些硬件经常变动但不重要，产生大量无用告警
**解决**: 禁用这些硬件的监控，只关注关键硬件

#### 场景2: 定制化监控
**问题**: 不同环境需要不同的监控策略
**解决**: 根据实际需求灵活配置监控项

#### 场景3: 分阶段部署
**问题**: 先监控核心硬件，后续逐步扩大范围
**解决**: 可以先启用CPU/内存，后续再启用其他

### 🧪 测试方法

#### 自动化测试
```bash
cd server
python test_alert_settings.py
```

测试覆盖：
- ✅ 获取告警设置
- ✅ 更新告警设置
- ✅ 验证设置生效
- ✅ 恢复默认设置

#### 手动测试
1. 启动服务器: `python app.py`
2. 访问 http://localhost:5000
3. 点击"邮件配置"按钮
4. 切换到"告警设置"标签
5. 修改监控项并保存
6. 客户端上报数据验证告警触发

### 📊 性能影响

- **数据库**: 新增1个表，仅1行记录，无性能影响
- **API**: 新增2个简单查询接口，响应时间 < 10ms
- **硬件对比**: 增加条件判断，性能影响可忽略
- **总体**: 对系统性能无明显影响

### 🔒 安全性

- 告警设置为全局配置，所有用户共享
- 无需额外权限控制（继承现有系统权限）
- 不涉及敏感数据，无安全风险

### 📝 兼容性

- ✅ 向后兼容：不影响现有功能
- ✅ 数据库兼容：自动创建新表，不影响旧数据
- ✅ API兼容：新增接口，不修改现有接口
- ✅ 前端兼容：扩展现有模态框，不破坏原有布局

### ⚠️ 注意事项

1. **首次使用**: 系统会自动创建默认配置，无需手动初始化
2. **设置生效**: 修改后立即生效，无需重启服务
3. **历史数据**: 不影响已有的基准数据和告警记录
4. **全局设置**: 当前为全局配置，对所有客户端统一生效

### 🚀 后续计划

可能的增强方向：
- [ ] 支持按分组设置不同的监控规则
- [ ] 支持按客户端单独配置
- [ ] 添加监控规则的导入/导出
- [ ] 提供预设模板（标准、严格、宽松等）
- [ ] 添加监控规则的生效时间范围

### 📞 技术支持

如有问题或建议，请：
1. 查阅 `告警设置功能说明.md`
2. 参考 `告警设置快速开始.md`
3. 运行测试脚本验证功能
4. 联系开发团队

---

**更新日期**: 2026-05-14  
**版本**: v4.2  
**作者**: 硬件监控系统开发团队
