# 页面切换报错修复

日期：2026-10-23。报错：destroy is not a function。

## 原因与修改

app/components/Dashboard.tsx里的Review和Policy将返回Promise的load直接传给useEffect。React离开组件时尝试把这个返回值当清理函数调用，因此出错。不是后端断开、模型拒绝或内存不足。

现在通过useCallback稳定load函数，再在不返回Promise的effect中调用：

```tsx
useEffect(() => { void load(); }, [load]);
```

保留原有异步加载、错误处理和Prompt操作后的刷新行为；没有修改后端、API密钥或业务数据。

## 修复前后的实际浏览器验证

最初的交互浏览器通道初始化失败，随后使用已有Playwright运行时启动独立无界面浏览器进行回归，不操作用户浏览器。没有下载或安装新依赖。

新增tests/navigation-lifecycle.test.mjs，针对三个场景反复进入/退出人工复核和Prompt页面：

1. 请求正常返回后切换。
2. 请求仍在等待时离开。
3. 只读接口返回503错误时切换。

修复前3个场景均失败，浏览器日志捕获非法effect返回值警告及与截图一致的destroy异常。修复后3个场景均通过，每个7次导航，共21次导航，没有运行时异常或清理函数警告。

所有/api/请求均被测试夹具拦截，任何非GET或未知接口请求都会使测试失败。因此没有触发真实分析、修改记录或调用模型，新增模型Token为0。它验证的是浏览器组件生命周期，不替代真实后端业务验收。

原始记录位于.tmp/navigation-lifecycle，修复前文件以before-fix-开头，修复后同名场景文件保存当前结果；该目录被Git忽略。

另外前端5项单元测试、2项页面渲染/密钥隔离检查、ESLint和生产构建全部通过。

## 如何复现测试

package.json新增test:navigation命令。先启动本地前端，再执行npm run test:navigation。默认测试地址http://localhost:3000，可通过NAVIGATION_TEST_URL指定其他本地地址。

需要已安装的Playwright与可用Chromium/Chrome；若Playwright不在项目依赖中，可用PLAYWRIGHT_MODULE_PATH指定现成的playwright包目录。本机验证使用工作区内置运行时。测试不会自动下载浏览器，也不会自动调用后端模型。

## 用户现在如何恢复页面

在原页面按Ctrl+F5重新加载，再切换“人工复核”和“Prompt 与规则”。前端开发服务会使用最新代码；无须更换密钥或修改模型配置。
