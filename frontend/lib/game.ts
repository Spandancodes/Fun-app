export type Direction = "up" | "down" | "left" | "right";
export type Point = { x: number; y: number };
export type Game = {
  snake: Point[];
  yes: Point;
  no: Point;
  noCount: number;
  turn: number;
};
export const SIZE = 7;
const NO_SPOTS: Point[] = [
  { x: 1, y: 3 },
  { x: 2, y: 1 },
  { x: 5, y: 5 },
  { x: 1, y: 5 },
];

export function newGame(): Game {
  return {
    snake: [
      { x: 3, y: 3 },
      { x: 3, y: 4 },
      { x: 3, y: 5 },
      { x: 3, y: 6 },
      { x: 2, y: 6 },
    ],
    yes: { x: 5, y: 3 },
    no: NO_SPOTS[0],
    noCount: 0,
    turn: 0,
  };
}

export function advance(
  game: Game,
  direction: Direction,
): { game: Game; catch: "yes" | "no" | null } {
  const delta = {
    up: { x: 0, y: -1 },
    down: { x: 0, y: 1 },
    left: { x: -1, y: 0 },
    right: { x: 1, y: 0 },
  }[direction];
  const head = game.snake[0];
  const next = {
    x: Math.max(0, Math.min(SIZE - 1, head.x + delta.x)),
    y: Math.max(0, Math.min(SIZE - 1, head.y + delta.y)),
  };
  if (next.x === head.x && next.y === head.y) return { game, catch: null };
  const snake = [next, ...game.snake.slice(0, -1)];
  const base = { ...game, snake, turn: game.turn + 1 };
  if (next.x === game.yes.x && next.y === game.yes.y)
    return { game: base, catch: "yes" };
  if (next.x === game.no.x && next.y === game.no.y) {
    const noCount = Math.min(game.noCount + 1, 3);
    return {
      game: { ...base, noCount, no: NO_SPOTS[noCount] },
      catch: "no",
    };
  }
  return { game: base, catch: null };
}
