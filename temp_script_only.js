
        // ─────────────────────────────────────────────
        // 전역 상태
        // ─────────────────────────────────────────────
        let allItems = [];   // 원본 전체
        let filteredItems = [];   // 필터 적용 후
        let currentPage = 1;
        let pageSize = 20;
        let sortCol = 'usbdCnt';
        let sortDir = 'desc';    // 'asc' | 'desc'

        // ─────────────────────────────────────────────
        // 초기화
        // ─────────────────────────────────────────────
        function init() {
            try {
                if (typeof ONBID_DATA !== 'undefined' && ONBID_DATA && Array.isArray(ONBID_DATA.items)) {
                    allItems = ONBID_DATA.items;
                    filteredItems = [...allItems];

                    // 상태바 갱신
                    document.getElementById('statusBar').style.borderLeftColor = '#2d8a4e';
                    document.getElementById('statusBar').querySelector('.status-icon').textContent = '✅';
                    document.getElementById('statusBar').querySelector('.data-status-text').innerHTML =
                        `온비드 공매 데이터 로드 완료 &nbsp;|&nbsp; <strong>${allItems.length}건</strong> (유찰 2회 이상 임야)`;
                    document.getElementById('updateTime').textContent = `최종 갱신: ${ONBID_DATA.updatedAt || '알 수 없음'}`;
                    document.getElementById('btnRefresh').disabled = false;
                } else {
                    handleDataError();
                }
            } catch (e) {
                console.error('ONBID_DATA 로드 오류:', e);
                handleDataError();
            }
            applyFilters();
        }

        function handleDataError() {
            allItems = [];
            filteredItems = [];
            document.getElementById('statusBar').style.borderLeftColor = '#e05a5a';
            document.getElementById('statusBar').querySelector('.status-icon').textContent = '⚠️';
            document.getElementById('statusBar').querySelector('.data-status-text').innerHTML =
                '<strong style="color:#c0392b;">데이터 파일(onbid_data.js)을 찾을 수 없습니다.</strong> &nbsp;→ fetch_onbid.py를 먼저 실행하세요.';
            document.getElementById('btnRefresh').disabled = false;

            document.getElementById('resultBody').innerHTML = `
            <tr><td colspan="8">
                <div class="state-box">
                    <div class="state-icon">📂</div>
                    <p><strong>데이터 파일이 없습니다.</strong><br>
                    <code>fetch_onbid.py</code>를 실행하면 <code>onbid_data.js</code>가 생성됩니다.</p>
                    <p class="state-hint">명령 프롬프트에서: python fetch_onbid.py<br>또는 run_fetch.bat 실행</p>
                </div>
            </td></tr>`;
            document.getElementById('resultCount').textContent = '0';
        }

        function reloadData() {
            location.reload();
        }

        // ─────────────────────────────────────────────
        // 필터링
        // ─────────────────────────────────────────────
        function applyFilters() {
            const region = document.getElementById('filterRegion').value.trim();
            const usbdMin = parseInt(document.getElementById('filterUsbdMin').value) || 2;
            const addrKw = document.getElementById('filterAddr').value.trim();

            filteredItems = allItems.filter(item => {
                const addr = item.addr || '';
                if (region && !addr.includes(region)) return false;
                if ((item.usbdCnt || 0) < usbdMin) return false;
                if (addrKw && !addr.includes(addrKw)) return false;
                return true;
            });

            currentPage = 1;
            sortAndRender();
        }

        function resetFilters() {
            document.getElementById('filterRegion').value = '';
            document.getElementById('filterUsbdMin').value = '2';
            document.getElementById('filterAddr').value = '';
            applyFilters();
        }

        // ─────────────────────────────────────────────
        // 정렬
        // ─────────────────────────────────────────────
        function applySort() {
            const v = document.getElementById('sortSelect').value;
            if (v === 'usbdDesc') { sortCol = 'usbdCnt'; sortDir = 'desc'; }
            else if (v === 'usbdAsc') { sortCol = 'usbdCnt'; sortDir = 'asc'; }
            else if (v === 'apprDesc') { sortCol = 'apprAmtRaw'; sortDir = 'desc'; }
            else if (v === 'apprAsc') { sortCol = 'apprAmtRaw'; sortDir = 'asc'; }
            else if (v === 'minbidDesc') { sortCol = 'minBidAmtRaw'; sortDir = 'desc'; }
            else if (v === 'minbidAsc') { sortCol = 'minBidAmtRaw'; sortDir = 'asc'; }
            else if (v === 'bidEdAsc') { sortCol = 'bidEdDt'; sortDir = 'asc'; }
            currentPage = 1;
            sortAndRender();
        }

        function sortByCol(col) {
            if (sortCol === col) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
            else { sortCol = col; sortDir = 'desc'; }
            currentPage = 1;
            sortAndRender();
        }

        function sortAndRender() {
            const dir = sortDir === 'asc' ? 1 : -1;

            filteredItems.sort((a, b) => {
                let va = a[sortCol] ?? '';
                let vb = b[sortCol] ?? '';
                if (typeof va === 'string' && typeof vb === 'string') {
                    return va.localeCompare(vb, 'ko') * dir;
                }
                return (va - vb) * dir;
            });

            // 헤더 화살표 갱신
            document.querySelectorAll('.result-table thead th').forEach(th => {
                th.classList.remove('sort-asc', 'sort-desc');
            });

            renderTable();
            renderPagination();
        }

        function changePageSize() {
            pageSize = parseInt(document.getElementById('pageSize').value);
            currentPage = 1;
            renderTable();
            renderPagination();
        }

        // ─────────────────────────────────────────────
        // 테이블 렌더링
        // ─────────────────────────────────────────────
        function renderTable() {
            const tbody = document.getElementById('resultBody');
            document.getElementById('resultCount').textContent = filteredItems.length.toLocaleString();

            if (filteredItems.length === 0) {
                tbody.innerHTML = `<tr><td colspan="8">
                <div class="state-box">
                    <div class="state-icon">🔍</div>
                    <p>검색 조건에 맞는 물건이 없습니다.<br>조건을 변경하거나 초기화 버튼을 눌러보세요.</p>
                </div>
            </td></tr>`;
                return;
            }

            const start = (currentPage - 1) * pageSize;
            const end = Math.min(start + pageSize, filteredItems.length);
            const rows = filteredItems.slice(start, end);

            tbody.innerHTML = rows.map((item, idx) => buildRow(item, start + idx + 1)).join('');
        }

        function buildRow(item, no) {
            // 유찰 배지 색상
            let usbdClass = 'usbd-2';
            if (item.usbdCnt >= 10) usbdClass = 'usbd-high';
            else if (item.usbdCnt >= 3) usbdClass = 'usbd-3';

            // 입찰기간 남은날
            const remainHtml = calcRemain(item.bidEdDt);

            // 감정가 낙찰률
            let rateHtml = '';
            if (item.apprAmtRaw > 0 && item.minBidAmtRaw > 0) {
                const rate = ((item.minBidAmtRaw / item.apprAmtRaw) * 100).toFixed(0);
                rateHtml = `<div class="price-rate">감정가 대비 ${rate}%</div>`;
            }

            // 면적
            const area = item.area ? `${parseFloat(item.area).toLocaleString('ko')} ㎡` : '-';

            return `
        <tr>
            <td class="col-no">${no}</td>
            <td class="col-addr">
                <a href="#" onclick="goOnbid('${item.cltrNo}','${item.pbctNo}');return false;" class="prop-id">${escHtml(item.cltrNo || '-')}</a>
                <div class="prop-addr-text">${escHtml(item.addr || '-')}</div>
                <div class="prop-tags">
                    <span class="tag tag-forest">임야</span>
                    <span class="tag tag-bid">${escHtml(item.bidDivNm || '일반입찰')}</span>
                    ${item.orgNm ? `<span class="tag tag-org">${escHtml(item.orgNm)}</span>` : ''}
                </div>
            </td>
            <td class="col-area">${area}</td>
            <td class="col-usbd"><span class="usbd-badge ${usbdClass}">${item.usbdCnt}회</span></td>
            <td class="col-appr">
                <div class="price-main">${escHtml(item.apprAmt || '-')}</div>
            </td>
            <td class="col-minbid">
                <div class="price-main">${escHtml(item.minBidAmt || '-')}</div>
                ${rateHtml}
            </td>
            <td class="col-period">
                ${remainHtml}
                <div class="period-date">
                    ${fmtDate(item.bidBgDt)}<br>
                    <span style="color:#aaa">~</span><br>
                    ${fmtDate(item.bidEdDt)}
                </div>
            </td>
            <td class="col-action">
                <a href="#" onclick="goOnbid('${item.cltrNo}','${item.pbctNo}');return false;" class="btn-onbid">상세보기</a>
            </td>
        </tr>`;
        }

        // ─────────────────────────────────────────────
        // 페이지네이션
        // ─────────────────────────────────────────────
        function renderPagination() {
            const totalPages = Math.ceil(filteredItems.length / pageSize);
            const el = document.getElementById('paginationArea');
            if (totalPages <= 1) { el.innerHTML = ''; return; }

            const blockSize = 10;
            const blockStart = Math.floor((currentPage - 1) / blockSize) * blockSize + 1;
            const blockEnd = Math.min(blockStart + blockSize - 1, totalPages);

            let html = '';
            html += `<button class="page-btn arrow" onclick="goPage(1)" ${currentPage === 1 ? 'data-disabled="true"' : ''}>◀◀</button>`;
            html += `<button class="page-btn arrow" onclick="goPage(${currentPage - 1})" ${currentPage === 1 ? 'data-disabled="true"' : ''}>◀</button>`;

            for (let i = blockStart; i <= blockEnd; i++) {
                html += `<button class="page-btn ${i === currentPage ? 'active' : ''}" onclick="goPage(${i})">${i}</button>`;
            }

            html += `<button class="page-btn arrow" onclick="goPage(${currentPage + 1})" ${currentPage === totalPages ? 'data-disabled="true"' : ''}>▶</button>`;
            html += `<button class="page-btn arrow" onclick="goPage(${totalPages})" ${currentPage === totalPages ? 'data-disabled="true"' : ''}>▶▶</button>`;
            html += `<span class="page-info">${currentPage} / ${totalPages} 페이지</span>`;

            el.innerHTML = html;
        }

        function goPage(p) {
            const totalPages = Math.ceil(filteredItems.length / pageSize);
            if (p < 1 || p > totalPages) return;
            currentPage = p;
            renderTable();
            renderPagination();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        // ─────────────────────────────────────────────
        // CSV 다운로드
        // ─────────────────────────────────────────────
        function exportCSV() {
            if (filteredItems.length === 0) { alert('내보낼 데이터가 없습니다.'); return; }
            const headers = ['물건번호', '소재지', '면적', '유찰횟수', '감정가', '최저입찰가', '입찰시작', '입찰마감', '집행기관'];
            const rows = filteredItems.map(item => [
                item.cltrNo, item.addr, item.area,
                item.usbdCnt, item.apprAmt, item.minBidAmt,
                item.bidBgDt, item.bidEdDt, item.orgNm
            ].map(v => `"${String(v || '').replace(/"/g, '""')}"`));

            const csv = '\uFEFF' + [headers, ...rows].map(r => r.join(',')).join('\r\n');
            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `onbid_forest_${new Date().toISOString().split('T')[0]}.csv`;
            a.click();
        }

        // ─────────────────────────────────────────────
        // 온비드 물건 조회 연결
        // ─────────────────────────────────────────────
        function goOnbid(cltrMngNo, pbctCdtnNo) {
            const win = window.open('about:blank', '_blank');
            if (!win) {
                alert('팝업이 차단되었습니다. 팝업 허용 후 다시 시도해 주세요.');
                return;
            }
            // 배열+join 방식으로 작성 (template literal 내 script 태그 충돌 방지)
            const sc = 'script';
            const html = [
                '<!DOCTYPE html>',
                '<html><head><meta charset="UTF-8">',
                '<title>온비드 물건 조회 - ' + cltrMngNo + '</title>',
                '<style>',
                '*{margin:0;padding:0;box-sizing:border-box;}',
                'body{font-family:sans-serif;background:#f0f4f8;padding:24px;}',
                '.card{background:#fff;border-radius:10px;padding:24px 28px;max-width:620px;margin:0 auto;',
                '  box-shadow:0 4px 16px rgba(0,0,0,0.1);border-left:5px solid #2d8a4e;}',
                'h2{color:#1a5c2e;font-size:18px;margin-bottom:16px;}',
                '.num-box{background:#e8f4e8;border:1px solid #b8ddc3;border-radius:6px;',
                '  padding:10px 16px;font-size:16px;font-weight:700;color:#1a5c2e;',
                '  display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;}',
                '.copy-btn{background:#1a5c2e;color:#fff;border:none;padding:6px 14px;',
                '  border-radius:4px;font-size:13px;cursor:pointer;}',
                '.copy-btn:hover{background:#144a25;}',
                '.guide{background:#fffbe6;border:1px solid #ffe58f;border-radius:6px;',
                '  padding:14px 16px;font-size:13px;color:#614700;line-height:1.9;margin-bottom:16px;}',
                '.guide strong{color:#1a5c2e;}',
                '.guide ol{margin:6px 0 0 18px;}',
                '.btn-onbid{display:block;text-align:center;background:#1a5c2e;color:#fff;',
                '  text-decoration:none;padding:12px;border-radius:6px;font-size:15px;font-weight:700;}',
                '.btn-onbid:hover{background:#144a25;}',
                '.copied{color:#2d8a4e;font-size:12px;margin-left:8px;display:none;}',
                '</style></head><body>',
                '<div class="card">',
                '  <h2>🌲 온비드 물건 조회</h2>',
                '  <div class="num-box">',
                '    <span>' + cltrMngNo + '</span>',
                '    <span>',
                '      <button class="copy-btn" onclick="doCopy()">📋 번호 복사</button>',
                '      <span class="copied" id="copiedMsg">✓ 복사됨</span>',
                '    </span>',
                '  </div>',
                '  <div class="guide">',
                '    <strong>📌 온비드에서 해당 물건 조회 방법 (3단계)</strong>',
                '    <ol>',
                '      <li>아래 <strong>[온비드 열기]</strong> 버튼 클릭</li>',
                '      <li>온비드 검색 화면 상단 <strong>"상세보기"</strong> 클릭 →',
                '          <strong>물건관리번호</strong> 입력란에 <strong>' + cltrMngNo + '</strong> 붙여넣기(Ctrl+V)</li>',
                '      <li><strong>[검색]</strong> 버튼 클릭 → 해당 물건 1건 조회</li>',
                '    </ol>',
                '  </div>',
                '  <a class="btn-onbid" href="https://www.onbid.co.kr/op/cta/cltrdtl/collateralDetailRealEstateList.do" target="_blank">',
                '    🔗 온비드 열기',
                '  </a>',
                '</div>',
                '<' + sc + '>',
                '  var numText = "' + cltrMngNo + '";',
                '  function doCopy() {',
                '    if (navigator.clipboard) {',
                '      navigator.clipboard.writeText(numText).then(showCopied).catch(fallbackCopy);',
                '    } else { fallbackCopy(); }',
                '  }',
                '  function fallbackCopy() {',
                '    var t = document.createElement("textarea");',
                '    t.value = numText; document.body.appendChild(t); t.select();',
                '    document.execCommand("copy"); document.body.removeChild(t); showCopied();',
                '  }',
                '  function showCopied() {',
                '    var el = document.getElementById("copiedMsg");',
                '    el.style.display = "inline";',
                '    setTimeout(function(){ el.style.display = "none"; }, 2500);',
                '  }',
                '  window.onload = function() { doCopy(); };',
                '</' + sc + '>',
                '</body></html>'
            ].join('\n');
            win.document.write(html);
            win.document.close();
        }

        // ─────────────────────────────────────────────
        // 유틸리티
        // ─────────────────────────────────────────────
        function escHtml(str) {
            return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        function fmtDate(dt) {
            if (!dt) return '-';
            return String(dt).replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3').substring(0, 10);
        }

        function calcRemain(edDt) {
            if (!edDt) return '';
            const dateStr = String(edDt).replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3').substring(0, 10);
            const diff = new Date(dateStr) - new Date();
            const days = Math.floor(diff / 86400000);
            if (days < 0) return `<div class="period-remain">마감</div>`;
            if (days === 0) return `<div class="period-remain" style="color:#cc0000;">오늘 마감!</div>`;
            if (days <= 3) return `<div class="period-remain" style="color:#cc0000;">D - ${days}</div>`;
            if (days <= 7) return `<div class="period-remain" style="color:#e07000;">D - ${days}</div>`;
            return `<div class="period-remain" style="color:#888;">D - ${days}</div>`;
        }

        // ─────────────────────────────────────────────
        // Enter key 검색
        // ─────────────────────────────────────────────
        document.getElementById('filterAddr').addEventListener('keydown', function (e) {
            if (e.key === 'Enter') applyFilters();
        });

        // ─────────────────────────────────────────────
        // 페이지 로드 시 실행
        // ─────────────────────────────────────────────
        window.addEventListener('load', init);
    