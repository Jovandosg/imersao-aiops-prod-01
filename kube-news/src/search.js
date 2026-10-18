const { Op } = require('sequelize');

// Devolve as palavras do termo. Lista vazia significa "sem termo".
const parseTerm = (q) => {
    if (typeof q !== 'string') {
        return [];
    }
    return q.trim().split(/\s+/).filter((w) => w.length > 0);
};

// A barra vem primeiro para não escapar duas vezes.
const escapeLike = (w) => {
    return w.replace(/\\/g, '\\\\').replace(/%/g, '\\%').replace(/_/g, '\\_');
};

const buildWhere = (words) => {
    return {
        [Op.and]: words.map((w) => {
            const pattern = '%' + escapeLike(w) + '%';
            return {
                [Op.or]: [
                    { title: { [Op.iLike]: pattern } },
                    { summary: { [Op.iLike]: pattern } },
                ],
            };
        }),
    };
};

module.exports = { parseTerm, escapeLike, buildWhere };
