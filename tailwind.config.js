/** Tailwind 构建配置 — 生成静态 app.css, 替换生产禁用的 Play CDN.

为什么: base.html 原用 https://cdn.tailwindcss.com (Play CDN), 它在浏览器里
实时 JIT 编译 CSS → 阻塞首屏、渐变卡"慢慢上色"。改为构建期预编译静态 CSS。

构建 (本机有 node 即可, VPS 无需 node):
  npx tailwindcss@3 -i src/dashboard/static/tailwind.input.css \
    -o src/dashboard/static/app.css --minify

content 必须覆盖所有出现 class 的地方 (html 模板 + 传 class 字符串的 py + js)。
*/
module.exports = {
  content: [
    "./src/dashboard/templates/**/*.html",
    "./src/dashboard/**/*.py",
    "./src/dashboard/static/**/*.js",
  ],
  // 不覆盖 theme.colors: 旧 inline config 把 emerald/rose/amber 定成扁平色会
  // 抹掉默认整条色阶 (emerald-600 等全挂), 且这些扁平名根本没当 class 用。
  theme: { extend: {} },
};
