const { describe, it, before } = require('node:test');
const assert = require('node:assert');

const BASE_URL = process.env.BASE_URL || 'http://localhost:8080';

// Prefixo aleatório por execução: isola as notícias deste teste dos dados já existentes
const P = 'kn' + Math.random().toString(36).slice(2, 10);
const M = (n) => `${P}x${String(n).padStart(2, '0')}`;

const NO_RESULTS = 'Nenhuma notícia encontrada para';
const EMPTY_BASE = 'Ainda não temos nenhum post';

const POSTS = [
    { title: `${M(1)} Kubernetes na prática`, resumo: 'resumo comum', description: 'conteudo' },
    { title: `${M(2)} titulo`, resumo: `${P}resumoonly palavra`, description: 'conteudo' },
    { title: `${M(3)} titulo`, resumo: 'resumo', description: `${P}conteudoonly` },
    { title: `${M(4)} ${P}dup`, resumo: `${P}dup`, description: 'conteudo' },
    { title: `${M(5)} deploy`, resumo: 'cluster', description: 'conteudo' },
    { title: `${M(6)} deploy`, resumo: 'outro', description: 'conteudo' },
    { title: `${M(7)} Notícia do cluster`, resumo: 'resumo', description: 'conteudo' },
    { title: `${M(8)} 50%`, resumo: 'resumo', description: 'conteudo' },
    { title: `${M(9)} 50 por cento`, resumo: 'resumo', description: 'conteudo' },
    { title: `${M(10)} it's "quoted"`, resumo: 'back\\slash', description: 'conteudo' },
];

const createPosts = async (artigos) => {
    const res = await fetch(`${BASE_URL}/api/post`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ artigos }),
    });
    assert.strictEqual(res.status, 200);
};

const get = async (query) => {
    const res = await fetch(`${BASE_URL}/${query}`);
    const html = await res.text();
    return { status: res.status, html };
};

const search = (term) => get(`?q=${encodeURIComponent(term)}`);

// Marcadores das notícias deste teste presentes no HTML
const found = (html) => {
    const re = new RegExp(`${P}x\\d\\d`, 'g');
    return [...new Set(html.match(re) || [])].sort();
};

describe('busca de notícias', () => {
    before(async () => {
        await createPosts(POSTS);
    });

    describe('correspondência', () => {
        it('encontra por título', async () => {
            const { html } = await search(`${P} prática`);
            assert.deepStrictEqual(found(html), [M(1)]);
        });

        it('encontra por resumo', async () => {
            const { html } = await search(`${P}resumoonly`);
            assert.deepStrictEqual(found(html), [M(2)]);
        });

        it('encontra trecho de palavra', async () => {
            const { html } = await search(`${P} kube`);
            assert.deepStrictEqual(found(html), [M(1)]);
        });

        it('ignora o conteúdo', async () => {
            const { html } = await search(`${P}conteudoonly`);
            assert.deepStrictEqual(found(html), []);
            assert.ok(html.includes(NO_RESULTS));
        });

        it('notícia com o termo no título e no resumo aparece uma vez', async () => {
            const { html } = await search(`${P}dup`);
            assert.deepStrictEqual(found(html), [M(4)]);
            assert.strictEqual(html.split(M(4)).length - 1, 1);
        });

        it('várias palavras distribuídas entre título e resumo', async () => {
            const { html } = await search(`${P} deploy cluster`);
            assert.deepStrictEqual(found(html), [M(5)]);
        });

        it('falta uma das palavras', async () => {
            const { html } = await search(`${P} deploy cluster`);
            assert.ok(!found(html).includes(M(6)));
        });

        it('ordem das palavras é indiferente', async () => {
            const a = await search(`${P} deploy cluster`);
            const b = await search(`cluster deploy ${P}`);
            assert.deepStrictEqual(found(b.html), found(a.html));
        });
    });

    describe('caixa e acentos', () => {
        it('KUBERNETES e kubernetes dão o mesmo resultado', async () => {
            const upper = await search(`${P.toUpperCase()} KUBERNETES`);
            const lower = await search(`${P} kubernetes`);
            assert.deepStrictEqual(found(upper.html), [M(1)]);
            assert.deepStrictEqual(found(lower.html), [M(1)]);
        });

        it('NOTÍCIA encontra Notícia', async () => {
            const { html } = await search(`${P} NOTÍCIA`);
            assert.deepStrictEqual(found(html), [M(7)]);
        });

        it('noticia não encontra Notícia', async () => {
            const { html } = await search(`${P} noticia`);
            assert.deepStrictEqual(found(html), []);
        });
    });

    describe('termo literal', () => {
        it('% não é curinga', async () => {
            const { status, html } = await search(`${P} %`);
            assert.strictEqual(status, 200);
            assert.deepStrictEqual(found(html), [M(8)]);
        });

        it('_ não é curinga', async () => {
            const { status, html } = await search(`${P} _`);
            assert.strictEqual(status, 200);
            assert.deepStrictEqual(found(html), []);
            assert.ok(html.includes(NO_RESULTS));
        });

        it('barra invertida', async () => {
            const { status, html } = await search(`${P} \\`);
            assert.strictEqual(status, 200);
            assert.deepStrictEqual(found(html), [M(10)]);
        });

        it('aspas simples', async () => {
            const { status, html } = await search(`${P} '`);
            assert.strictEqual(status, 200);
            assert.deepStrictEqual(found(html), [M(10)]);
        });

        it('aspas duplas', async () => {
            const { status, html } = await search(`${P} "`);
            assert.strictEqual(status, 200);
            assert.deepStrictEqual(found(html), [M(10)]);
        });
    });

    describe('normalização e estados da tela', () => {
        it('q vazio exibe todas as notícias', async () => {
            const { status, html } = await get('?q=');
            assert.strictEqual(status, 200);
            assert.strictEqual(found(html).length, POSTS.length);
            assert.ok(!html.includes(NO_RESULTS));
        });

        it('q só com espaços exibe todas as notícias', async () => {
            const { status, html } = await get('?q=%20%20%20');
            assert.strictEqual(status, 200);
            assert.strictEqual(found(html).length, POSTS.length);
            assert.ok(!html.includes('posts-list__search-clear'));
        });

        it('espaços extras dão o mesmo resultado', async () => {
            const extra = await search(`  ${P}   deploy    cluster  `);
            const normal = await search(`${P} deploy cluster`);
            assert.deepStrictEqual(found(extra.html), found(normal.html));
            assert.ok(extra.html.includes(`value="${P} deploy cluster"`));
        });

        it('?q=a&q=b responde sem erro e exibe todas as notícias', async () => {
            const { status, html } = await get('?q=a&q=b');
            assert.strictEqual(status, 200);
            assert.strictEqual(found(html).length, POSTS.length);
        });

        it('?q[x]=y responde sem erro e exibe todas as notícias', async () => {
            const { status, html } = await get('?q[x]=y');
            assert.strictEqual(status, 200);
            assert.strictEqual(found(html).length, POSTS.length);
        });

        it('termo muito longo exibe a mensagem de nenhum resultado', async () => {
            const { status, html } = await search(P + 'z'.repeat(500));
            assert.strictEqual(status, 200);
            assert.ok(html.includes(NO_RESULTS));
        });

        it('campo continua preenchido com o termo', async () => {
            const { html } = await search(`${P} deploy`);
            assert.ok(html.includes(`name="q" value="${P} deploy"`));
        });

        it('link Limpar aparece só com termo', async () => {
            const withTerm = await search(`${P} deploy`);
            assert.ok(withTerm.html.includes('<a class="posts-list__search-clear" href="/">Limpar</a>'));

            const without = await get('');
            assert.ok(without.html.includes('name="q"'));
            assert.ok(!without.html.includes('posts-list__search-clear'));
        });

        it('nenhum resultado mostra a mensagem própria e não a de base vazia', async () => {
            const { html } = await search(`${P}inexistente`);
            assert.ok(html.includes(`${NO_RESULTS} "${P}inexistente"`));
            assert.ok(!html.includes(EMPTY_BASE));
            assert.ok(html.includes('name="q"'));
        });

        it('termo com HTML é escapado', async () => {
            const { status, html } = await search('<script>alert(1)</script>');
            assert.strictEqual(status, 200);
            assert.ok(!html.includes('<script>alert(1)</script>'));
            assert.ok(html.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));
        });
    });

    describe('resultado acessível por link', () => {
        it('a mesma URL devolve o mesmo resultado', async () => {
            const results = [];
            for (let i = 0; i < 5; i++) {
                const { html } = await search(`${P} deploy`);
                results.push(found(html));
            }
            for (const r of results) {
                assert.deepStrictEqual(r, [M(5), M(6)]);
            }
        });

        it('notícia criada depois entra no resultado', async () => {
            const before = await search(`${P}late`);
            assert.deepStrictEqual(found(before.html), []);

            await createPosts([{ title: `${M(11)} ${P}late`, resumo: 'resumo', description: 'conteudo' }]);

            const after = await search(`${P}late`);
            assert.deepStrictEqual(found(after.html), [M(11)]);
        });
    });
});
