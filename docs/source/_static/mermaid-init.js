(function() {
    // 儲存原始 Mermaid 原始碼
    function saveMermaidSource() {
        document.querySelectorAll('.mermaid').forEach(el => {
            if (!el.getAttribute('data-mermaid-source')) {
                el.setAttribute('data-mermaid-source', el.innerText);
            }
        });
    }

    // 取得適合的 Mermaid 主題
    function getMermaidTheme() {
        const bodyTheme = document.body.dataset.theme;
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        
        let theme = 'neutral'; // 預設淺色主題
        
        if (bodyTheme === 'dark') {
            theme = 'dark';
        } else if (bodyTheme === 'auto') {
            if (prefersDark) {
                theme = 'dark';
            }
        }
        
        console.log(`[AutoCRUD] Detected theme: ${bodyTheme}, System Dark: ${prefersDark} -> Mermaid Theme: ${theme}`);
        return theme;
    }

    // 重新渲染 Mermaid
    async function renderMermaid(retry = 0) {
        if (typeof mermaid === 'undefined') {
            if (retry < 10) {
                console.log(`[AutoCRUD] mermaid not defined, retrying (${retry + 1}/10)...`);
                setTimeout(() => renderMermaid(retry + 1), 300);
                return;
            }
            console.warn('[AutoCRUD] mermaid is not defined after 10 retries.');
            return;
        }

        const theme = getMermaidTheme();

        // 重置所有 mermaid 區塊
        document.querySelectorAll('.mermaid').forEach(el => {
            const source = el.getAttribute('data-mermaid-source');
            if (source) {
                el.innerHTML = source;
                el.removeAttribute('data-processed');
            }
        });

        // 重新初始化配置
        const config = {
            startOnLoad: false,
            theme: theme,
            securityLevel: 'loose', // 有時候需要這個
        };
        
        try {
            mermaid.initialize(config);
            
            // 根據 API 版本執行渲染
            if (typeof mermaid.run === 'function') {
                // Mermaid v10+
                await mermaid.run({
                    nodes: document.querySelectorAll('.mermaid')
                });
            } else if (typeof mermaid.init === 'function') {
                // Older Mermaid
                mermaid.init(undefined, document.querySelectorAll('.mermaid'));
            } else {
                console.error('[AutoCRUD] Cannot find mermaid.run or mermaid.init');
            }
            console.log('[AutoCRUD] Mermaid rendered successfully.');
        } catch (e) {
            console.error('[AutoCRUD] Mermaid render error:', e);
        }
    }

    // 當文件載入完成
    document.addEventListener('DOMContentLoaded', () => {
        saveMermaidSource();
        renderMermaid();

        // 監聽 Furo 主題變化
        const observer = new MutationObserver((mutations) => {
            let shouldRender = false;
            for (const mutation of mutations) {
                if (mutation.attributeName === 'data-theme') {
                    shouldRender = true;
                    break;
                }
            }
            if (shouldRender) {
                // 稍微延遲一下確保 DOM 狀態穩定
                setTimeout(renderMermaid, 50);
            }
        });

        observer.observe(document.body, { 
            attributes: true, 
            attributeFilter: ['data-theme'] 
        });
    });
})();

