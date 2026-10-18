const { describe, it } = require('node:test');
const assert = require('node:assert');
const { Op } = require('sequelize');
const { parseTerm, escapeLike, buildWhere } = require('../search');

describe('parseTerm', () => {
    it('devolve lista vazia quando q está ausente', () => {
        assert.deepStrictEqual(parseTerm(undefined), []);
    });

    it('devolve lista vazia quando q é vazio', () => {
        assert.deepStrictEqual(parseTerm(''), []);
    });

    it('devolve lista vazia quando q só tem espaços', () => {
        assert.deepStrictEqual(parseTerm('   '), []);
        assert.deepStrictEqual(parseTerm(' \t\n '), []);
    });

    it('remove espaços nas pontas e trata espaços repetidos como um separador', () => {
        assert.deepStrictEqual(parseTerm('  deploy    cluster  '), ['deploy', 'cluster']);
    });

    it('devolve lista vazia quando q é array', () => {
        assert.deepStrictEqual(parseTerm(['a', 'b']), []);
    });

    it('devolve lista vazia quando q é objeto', () => {
        assert.deepStrictEqual(parseTerm({ x: 'y' }), []);
    });

    it('devolve uma palavra', () => {
        assert.deepStrictEqual(parseTerm('kubernetes'), ['kubernetes']);
    });

    it('devolve várias palavras na ordem do termo', () => {
        assert.deepStrictEqual(parseTerm('deploy cluster kind'), ['deploy', 'cluster', 'kind']);
    });
});

describe('escapeLike', () => {
    it('escapa %', () => {
        assert.strictEqual(escapeLike('50%'), '50\\%');
    });

    it('escapa _', () => {
        assert.strictEqual(escapeLike('a_b'), 'a\\_b');
    });

    it('escapa \\', () => {
        assert.strictEqual(escapeLike('a\\b'), 'a\\\\b');
    });

    it('escapa a barra antes dos curingas, sem escapar duas vezes', () => {
        assert.strictEqual(escapeLike('\\%'), '\\\\\\%');
        assert.strictEqual(escapeLike('%_\\'), '\\%\\_\\\\');
    });

    it('não altera texto sem curingas', () => {
        assert.strictEqual(escapeLike("it's \"ok\""), "it's \"ok\"");
    });
});

describe('buildWhere', () => {
    const group = (pattern) => ({
        [Op.or]: [
            { title: { [Op.iLike]: pattern } },
            { summary: { [Op.iLike]: pattern } },
        ],
    });

    it('uma palavra gera um Op.or de title/summary com Op.iLike', () => {
        assert.deepStrictEqual(buildWhere(['kube']), { [Op.and]: [group('%kube%')] });
    });

    it('várias palavras geram um Op.and desses grupos', () => {
        assert.deepStrictEqual(buildWhere(['deploy', 'cluster']), {
            [Op.and]: [group('%deploy%'), group('%cluster%')],
        });
    });

    it('escapa os curingas de cada palavra', () => {
        assert.deepStrictEqual(buildWhere(['%']), { [Op.and]: [group('%\\%%')] });
    });

    it('nunca usa content', () => {
        const where = buildWhere(['a', 'b']);
        for (const g of where[Op.and]) {
            for (const cond of g[Op.or]) {
                assert.ok(!('content' in cond));
            }
        }
    });
});
